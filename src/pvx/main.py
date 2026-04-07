import argparse
import asyncio
import sys
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import ollama
import structlog
import uvicorn

from pvx.core.compressor import ContextCompressor
from pvx.core.config import AppConfig, load_config
from pvx.core.events import event_bus
from pvx.core.queue import TaskQueueEngine
from pvx.core.vram import VRAMManager, State
from pvx.models.claude import ClaudeCodeModel
from pvx.models.ollama import OllamaModel
from pvx.store.database import init_db, write_queue
from pvx.core.model_discovery import discover, log_discovery_summary

logger = structlog.get_logger()
log = structlog.get_logger()

# Idle VRAM eviction: unload the current model after this many seconds idle.
# Prevents pinning VRAM when no tasks are queued.
IDLE_UNLOAD_SECONDS = 120

# How often (in idle cycles) to prune completed tasks from memory.
# Each idle cycle is ~0.5s, so 60 cycles ≈ 30 seconds.
PRUNE_EVERY_N_IDLE_CYCLES = 60


# ---------------------------------------------------------------------------
# AppState — module-level singleton holding all initialised components
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    config: AppConfig
    vram: VRAMManager
    queue: TaskQueueEngine
    claude_model: ClaudeCodeModel
    compressor: ContextCompressor
    ollama_models: Dict[str, OllamaModel] = field(default_factory=dict)
    # Tracks which Ollama model is currently loaded in VRAM
    current_ollama_model: Optional[str] = None
    # Per-task output store — lets dependent tasks reference prior output as history
    task_outputs: Dict[str, str] = field(default_factory=dict)
    # Timestamp of the last completed task — used for idle VRAM eviction
    _last_task_completed_at: Optional[datetime] = None
    # Zombie confirmation counters — zombie fires only after N consecutive
    # low-utilisation polls to prevent false positives on slow/memory-bound GPUs
    _zombie_confirm_counts: Dict[str, int] = field(default_factory=dict)
    # Session-level telemetry for cost tracker
    session_token_counts: Dict[str, int] = field(default_factory=dict)
    session_compressions: int = 0


# Module-level singleton — None until `start()` initialises the platform.
app_state: Optional[AppState] = None


# ---------------------------------------------------------------------------
# Orchestration loop helpers
# ---------------------------------------------------------------------------

async def _unload_current_model(state: AppState) -> None:
    """
    Evict the current Ollama model from VRAM before switching to another.

    Uses the Ollama keep_alive=0 API (not pkill). Polls /api/ps to confirm
    eviction rather than relying on a fixed sleep — faster and more reliable.
    """
    if not state.current_ollama_model:
        return

    model_name = state.current_ollama_model
    if model_name in state.ollama_models:
        state.ollama_models[model_name].unload()  # keep_alive=0 to Ollama
    else:
        state.vram.unload_model(model_name)

    state.current_ollama_model = None
    state.vram.loaded_model = None
    state.vram.state = State.IDLE

    # Poll until Ollama confirms the model is gone (max 8 seconds)
    for _ in range(16):
        await asyncio.sleep(0.5)
        if model_name not in state.vram.get_actually_loaded_models():
            break
    else:
        logger.warning("model_unload_timeout",
                       model=model_name,
                       hint="Ollama may still hold VRAM")


def _build_task_history(task, state: AppState) -> list:
    """
    Build conversation history for a task from prior context.

    - If the task was preempted and has a resume_prompt, that becomes history.
    - If the task has dependencies, include the output of completed deps as context.
    - Otherwise return empty list (no prior context).
    """
    from pvx.models.base import Message
    history = []

    # Resumed from preemption — inject partial output as prior assistant turn
    if task.resume_prompt:
        history.append(Message(role="user",    content=task.prompt))
        history.append(Message(role="assistant", content=task.resume_prompt))
        return history

    # Dependency outputs — inject completed dep outputs as context
    for dep_id in task.depends_on:
        dep_output = state.task_outputs.get(dep_id)
        if dep_output:
            history.append(Message(role="assistant", content=f"[Context from {dep_id}]\n{dep_output}"))

    return history


async def orchestration_loop(state: AppState) -> None:
    """
    Main dispatch loop — picks the highest-priority eligible task, routes it
    to the correct model, runs generation, and records the outcome.
    """
    idle_cycles = 0

    while True:
        task = state.queue.get_next_task()

        if task is None:
            idle_cycles += 1
            vram_state = state.vram.poll()

            # Zombie detection with hysteresis — require N consecutive low-GPU
            # polls before acting, preventing false positives on slow/memory-bound
            # workloads where GPU utilisation naturally dips between operations.
            for t in state.queue.pending_tasks:
                if t.status == "running":
                    if state.vram.detect_zombie(t, vram_state):
                        count = state._zombie_confirm_counts.get(t.id, 0) + 1
                        state._zombie_confirm_counts[t.id] = count
                        if count >= 5:
                            del state._zombie_confirm_counts[t.id]
                            logger.warning("zombie_confirmed",
                                           task_id=t.id,
                                           consecutive_low_polls=5)
                            state.vram.handle_zombie(t)
                    else:
                        # GPU is active — reset the counter for this task
                        state._zombie_confirm_counts.pop(t.id, None)

            # Idle VRAM eviction — unload model when queue has been empty long enough
            if (state.current_ollama_model
                    and state._last_task_completed_at is not None
                    and (datetime.now() - state._last_task_completed_at).total_seconds()
                    > IDLE_UNLOAD_SECONDS):
                logger.info("idle_vram_eviction",
                            model=state.current_ollama_model,
                            idle_seconds=IDLE_UNLOAD_SECONDS)
                await _unload_current_model(state)

            # Periodic task pruning — keep in-memory list bounded
            if idle_cycles % PRUNE_EVERY_N_IDLE_CYCLES == 0:
                pruned = state.queue.prune_completed_tasks()
                if pruned:
                    logger.debug("tasks_pruned", count=pruned)
                # Also prune task_outputs dict to free output text memory
                done_ids = {t.id for t in state.queue.pending_tasks}
                stale_ids = [k for k in state.task_outputs if k not in done_ids]
                for k in stale_ids:
                    del state.task_outputs[k]

            await asyncio.sleep(0.5)
            continue

        idle_cycles = 0

        # Pre-start preemption check: if a higher-priority task arrived since
        # get_next_task() was called, hand back this task and let the higher-
        # priority one go first.
        pending_priorities = [
            t.priority for t in state.queue.pending_tasks
            if t.status == "pending" and t.id != task.id
        ]
        if pending_priorities:
            highest_waiting = max(pending_priorities)
            if state.queue.should_preempt(
                type("_T", (), {"priority": highest_waiting})(),
                task,
            ):
                state.queue.handle_preemption(
                    next(t for t in state.queue.pending_tasks
                         if t.priority == highest_waiting and t.status == "pending"),
                    task,
                )
                logger.info("task_preempted_before_start",
                            task_id=task.id, preempted_by_priority=highest_waiting)
                await asyncio.sleep(0)
                continue

        task.status = "running"
        task.started_at = datetime.now()
        model_name: str = task.model  # Claude Code has already decided the model

        try:
            # 1. Unload previous model if switching to a different one
            if (model_name != "claude"
                    and state.current_ollama_model is not None
                    and state.current_ollama_model != model_name):
                logger.info("model_switch_unloading",
                            from_model=state.current_ollama_model,
                            to_model=model_name)
                await _unload_current_model(state)

            # 2. Resolve model instance
            if model_name == "claude":
                model = state.claude_model
            else:
                if model_name not in state.ollama_models:
                    state.ollama_models[model_name] = OllamaModel(
                        model_name=model_name,
                        task_queue=state.queue,
                        current_task_id=task.id,
                    )
                model = state.ollama_models[model_name]
                state.vram.load_model(model_name)
                state.vram.start_generation()
                state.current_ollama_model = model_name

            # 3. Build history from resume context or dependency outputs
            history = _build_task_history(task, state)

            # 4. Compress context if it has grown too large
            pre_compress_len = len(history)
            history = state.compressor.maybe_compress(model_name, history)
            if len(history) < pre_compress_len:
                state.session_compressions += 1

            # 5. Generate
            result = model.generate(
                prompt=task.prompt,
                history=history,
                task_id=task.id,
            )

            # 6. Handle result
            if result.error:
                task.status = "failed"
                task.error = result.error
                event_bus.emit("TASK_FAILED",
                               {"task_id": task.id, "error": result.error})
            else:
                task.status = "done"
                task.output = result.content
                task.completed_at = datetime.now()
                state._last_task_completed_at = task.completed_at
                # Store output so dependent tasks can use it as history
                state.task_outputs[task.id] = result.content
                # Accumulate per-model token counts for cost tracker
                state.session_token_counts[model_name] = (
                    state.session_token_counts.get(model_name, 0) + result.tokens_used
                )
                event_bus.emit("TASK_COMPLETED", {
                    "task_id": task.id,
                    "model": model_name,
                    "tokens": result.tokens_used,
                    "duration_ms": result.duration_ms,
                })

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            logger.error("orchestration_error",
                         task_id=task.id,
                         error=str(exc),
                         hint="If this is unexpected, report at https://github.com/DLA10/PvX/issues")

        finally:
            if model_name != "claude":
                state.vram.end_generation()
            # Free the streaming buffer — output is now in task.output
            state.queue.release_streaming_buffer(task.id)

        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# FastAPI server wrapper
# ---------------------------------------------------------------------------

async def start_api_server(state: AppState) -> None:
    from pvx.api.app import app  # local import avoids circular-import at module level

    uv_config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(uv_config)
    await server.serve()


# ---------------------------------------------------------------------------
# Start entry point
# ---------------------------------------------------------------------------

def start() -> None:
    asyncio.run(_start_async())


async def _start_async() -> None:
    global app_state

    config = load_config()
    if config is None:
        logger.error("pvx_start_failed", reason="config_not_found")
        return

    await init_db()
    await write_queue.start()

    # Wire the write queue into the event bus so events are persisted
    event_bus.set_write_queue(write_queue)

    # VRAMManager reads safety buffer and zombie config values from config
    vram = VRAMManager(config=config)
    vram_state = vram.poll()

    # Register config-specified models so can_load() works even without discovery
    for m in config.models.local:
        if m.name not in vram.MODEL_VRAM_MB:
            vram.update_model_vram(m.name, m.vram_mb)

    # Auto-discover installed Ollama models
    discovery = discover(vram_total_mb=vram_state.total_mb)
    log_discovery_summary(discovery)

    # Register discovered VRAM estimates so can_load() knows about these models.
    # Discovery estimates are more accurate than config defaults (they account for
    # the actual quantization tag in the model name).
    for m in discovery.models:
        if m.fits_in_vram:
            vram.update_model_vram(m.name, m.vram_estimate_mb)

    # Update compression model only if not explicitly set in config
    if discovery.compression_model and config.context.compression_model in (
        "qwen2.5-coder:3b", ""
    ):
        config.context.compression_model = discovery.compression_model
        logger.info("pvx_compression_model_set", model=discovery.compression_model)

    queue = TaskQueueEngine(vram_manager=vram, config=config)
    claude_model = ClaudeCodeModel()
    compressor = ContextCompressor(vram_manager=vram, config=config)

    app_state = AppState(
        config=config,
        vram=vram,
        queue=queue,
        claude_model=claude_model,
        compressor=compressor,
        ollama_models={},
    )

    # Store size_gb per model so /api/models/available can return it without
    # re-querying Ollama on every request.
    app_state._discovery_size_gb = {m.name: m.size_gb for m in discovery.models}

    logger.info("pvx_started", api_url="http://localhost:8000", mcp="stdio")

    await asyncio.gather(
        start_api_server(app_state),
        orchestration_loop(app_state),
    )


def check_python_version() -> tuple[bool, bool]:
    ok = sys.version_info >= (3, 11)
    v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if ok:
        log.info("  ✅ Python 3.11+       found", version=v)
    else:
        log.error("  ❌ Python 3.11+       not found", version=v)
    return ok, False  # (is_ok, is_warning)


def check_uv() -> tuple[bool, bool]:
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
        version = result.stdout.strip().split(" ")[1]
        log.info("  ✅ uv                 found", version=version)
        return True, False
    except Exception:
        log.error("  ❌ uv                 not found")
        return False, False


def check_ollama() -> tuple[bool, bool]:
    try:
        ollama.list()
        log.info("  ✅ Ollama             running (localhost:11434)")
        return True, False
    except Exception:
        log.error("  ❌ Ollama             not found or not running",
                  hint="Install: curl -fsSL https://ollama.com/install.sh | sh")
        return False, False


def check_ollama_models(ollama_ok: bool) -> tuple[bool, bool]:
    if not ollama_ok:
        log.info("  ⏭️  Ollama models     skipped (Ollama not found)")
        return True, False
    try:
        discovery = discover()
        if not discovery.models:
            log.warning("  ⚠️  Ollama models     none installed",
                        hint="Run: ollama pull qwen2.5-coder:3b")
            return True, True
        for m in discovery.models:
            fits = "fits in VRAM" if m.fits_in_vram else "too large for VRAM"
            log.info(f"  ✅ {m.name:<45} {m.size_gb}GB  {m.capability}  {fits}")
        return True, False
    except Exception:
        log.info("  ⏭️  Ollama models     skipped (Ollama not found)")
        return True, False


def check_pynvml() -> tuple[bool, bool]:
    try:
        import importlib.util
        if importlib.util.find_spec("pynvml") is None:
            raise ImportError("pynvml not found")
        log.info("  ✅ pynvml             found")
        return True, False
    except ImportError:
        log.warning("  ⚠️  pynvml            not found (will fallback to nvidia-smi)")
        return True, True  # warning, not error


def check_nvidia_gpu() -> tuple[bool, bool]:
    try:
        import pynvml  # noqa: PLC0415
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        pynvml.nvmlShutdown()
        log.info("  ✅ NVIDIA GPU         detected",
                 name=name, vram_mb=mem.total // 1024 // 1024)
        return True, False
    except Exception:
        log.warning("  ⚠️  NVIDIA GPU        not found (CPU fallback active)")
        return True, True  # warning, not error


def check_claude_code() -> tuple[bool, bool]:
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            log.info("  ✅ Claude Code        found")
            return True, False
        raise Exception("non-zero return")
    except Exception:
        log.warning("  ⚠️  Claude Code       not found (optional)",
                    hint="Install: npm install -g @anthropic-ai/claude-code")
        return True, True  # warning, not error


def check_config() -> tuple[bool, bool]:
    cfg = load_config()
    if cfg is not None:
        log.info("  ✅ pvx.config.yaml    valid")
        return True, False
    else:
        log.error("  ❌ pvx.config.yaml    invalid or missing")
        return False, False


def doctor() -> None:
    log.info("Checking PvX dependencies...")

    python_ok, _ = check_python_version()
    uv_ok, _ = check_uv()
    ollama_ok, _ = check_ollama()
    models_ok, _ = check_ollama_models(ollama_ok)
    pynvml_ok, pynvml_warn = check_pynvml()
    gpu_ok, gpu_warn = check_nvidia_gpu()
    claude_ok, claude_warn = check_claude_code()
    config_ok, _ = check_config()

    checks = [
        (python_ok, False),
        (uv_ok, False),
        (ollama_ok, False),
        (models_ok, False),
        (pynvml_ok, pynvml_warn),
        (gpu_ok, gpu_warn),
        (claude_ok, claude_warn),
        (config_ok, False),
    ]

    errors = sum(1 for ok, warn in checks if not ok and not warn)
    warnings = sum(1 for ok, warn in checks if warn)

    if errors > 0:
        log.error(f"{errors} errors, {warnings} warnings. Fix errors before running pvx start.")
    else:
        log.info(f"0 errors, {warnings} warnings. Ready to run pvx start.")


def init_config() -> None:
    """
    Generate a starter pvx.config.yaml in the current working directory.

    Copies the bundled example config (which ships inside the Python package)
    to ./pvx.config.yaml. The file includes comments explaining every option.
    Edit it to match your installed Ollama models, then run `pvx doctor`.
    """
    dest = Path("pvx.config.yaml")
    if dest.exists():
        log.warning("pvx_config_already_exists",
                    path=str(dest.resolve()),
                    hint="Delete it first or edit it directly")
        return

    # The example config is bundled inside the package at install time
    src = Path(__file__).parent / "pvx.config.example.yaml"
    if not src.exists():
        log.error("pvx_example_config_missing",
                  hint="Reinstall pvx: uv tool install --force pvx")
        return

    import shutil
    shutil.copy(src, dest)
    log.info("pvx_config_created",
             path=str(dest.resolve()),
             next_steps=[
                 "1. Edit pvx.config.yaml — update model names to match `ollama list`",
                 "2. Run: pvx doctor",
                 "3. Run: pvx start",
             ])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PvX — hardware-aware AI orchestration platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pvx init       Create pvx.config.yaml in the current directory\n"
            "  pvx doctor     Check all dependencies and model availability\n"
            "  pvx start      Start the platform (API on :8000, MCP on stdio)\n\n"
            "Docs & issues: https://github.com/DLA10/PvX"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init",   help="Create pvx.config.yaml in the current directory")
    subparsers.add_parser("doctor", help="Check dependencies and model availability")
    subparsers.add_parser("start",  help="Start the PvX platform (API + MCP server)")

    args = parser.parse_args()

    if args.command == "init":
        init_config()
    elif args.command == "doctor":
        doctor()
    elif args.command == "start":
        start()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
