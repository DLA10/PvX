import argparse
import sys
import subprocess
import ollama
import structlog
from pvx.core.config import config

log = structlog.get_logger()


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
        models = ollama.list()
        pulled = [m.model for m in models.models] if hasattr(models, "models") else []
        required = ["qwen2.5-coder:14b", "deepseek-r1:7b", "qwen2.5-coder:3b"]
        statuses = [f"{m} ✓" if m in pulled else f"{m} ✗" for m in required]
        log.info("  ✅ Ollama models      " + "  ".join(statuses))
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
    if config is not None:
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


def start() -> None:
    log.info("Starting PvX Platform...")
    # TODO: Initialize FastAPI, VRAM monitor, Queue


def main() -> None:
    parser = argparse.ArgumentParser(description="PvX - Agentic multi-model orchestration platform")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Check dependencies")
    subparsers.add_parser("start", help="Start the PvX platform")

    args = parser.parse_args()

    if args.command == "doctor":
        doctor()
    elif args.command == "start":
        start()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
