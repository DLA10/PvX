from fastapi import APIRouter
import structlog

router = APIRouter(prefix="/api/models", tags=["models"])
logger = structlog.get_logger()


@router.get("/")
async def list_models() -> list:
    """List all models known to PvX — both config-specified and discovered."""
    from pvx.main import app_state

    if app_state is None:
        return []

    local = list(app_state.vram.MODEL_VRAM_MB.keys())
    result = [m for m in local if m != "claude"] + ["claude"]
    return result


@router.get("/available")
async def list_available_models() -> dict:
    """
    Rich model catalogue for Claude Code to use when deciding routing.

    Returns every installed Ollama model with:
    - VRAM requirements and whether it can load right now
    - Capability description (what it is good for)
    - Whether it is currently loaded in VRAM
    - GPU summary

    Claude Code should call this at session start, discuss the options with
    the user, agree on a routing plan, and then use explicit model= params
    in submit_task() calls rather than relying on PvX auto-routing.
    """
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started", "models": []}

    vram_state   = app_state.vram.poll()
    actually_loaded = app_state.vram.get_actually_loaded_models()

    # Pull discovery metadata from the last run stored in main
    # Fall back to VRAM table alone if discovery isn't stored
    discovery_meta: dict = getattr(app_state, "_discovery_meta", {})

    models = []
    for name, vram_mb in app_state.vram.MODEL_VRAM_MB.items():
        if name == "claude":
            continue

        meta     = discovery_meta.get(name, {})
        cap      = meta.get("capability", _infer_capability(name))
        tier     = meta.get("tier", "unknown")
        size_gb  = meta.get("size_gb", round(vram_mb / 1024, 1))
        suggested = meta.get("suggested_for", _suggest_categories(cap, vram_mb))

        is_loaded  = name in actually_loaded or app_state.vram.loaded_model == name
        can_load   = app_state.vram.can_load(name)

        models.append({
            "name":             name,
            "capability":       cap,
            "tier":             tier,
            "size_gb":          size_gb,
            "vram_required_mb": vram_mb,
            "can_load_now":     can_load,
            "currently_loaded": is_loaded,
            "status":           "loaded" if is_loaded else ("available" if can_load else "too_large"),
            "suggested_for":    suggested,
        })

    # Sort: loaded first, then available, then too_large
    _order = {"loaded": 0, "available": 1, "too_large": 2}
    models.sort(key=lambda m: _order.get(m["status"], 9))

    return {
        "models": models,
        "claude": {
            "name":        "claude",
            "capability":  "architecture, large-context reasoning, final review, ambiguous classification",
            "cost":        "Pro subscription — no marginal API cost",
            "suggested_for": ["architecture", "final_review", "large_context",
                              "codebase_analysis", "ambiguous tasks"],
        },
        "gpu": {
            "total_mb":          vram_state.total_mb,
            "used_mb":           vram_state.used_mb,
            "free_mb":           vram_state.free_mb,
            "gpu_utilisation_pct": vram_state.gpu_utilisation_pct,
        },
        "constraint": (
            "Only one Ollama model can be resident in VRAM at a time on this GPU. "
            "Switching models takes 5–15 seconds cold-start. "
            "PvX batches same-model tasks together to minimise swaps."
        ),
    }


def _infer_capability(name: str) -> str:
    n = name.lower()
    if "coder" in n or "code" in n:
        return "code generation"
    if "deepseek-r1" in n or "qwq" in n:
        return "reasoning / chain-of-thought"
    if "gemma" in n or "llama" in n or "mistral" in n or "phi" in n:
        return "general purpose"
    return "general purpose"


def _suggest_categories(capability: str, vram_mb: int) -> list:
    if "code" in capability:
        if vram_mb >= 5000:
            return ["complex_code", "algorithm_design", "ml_pipeline",
                    "oop_design", "code_review", "system_design"]
        return ["boilerplate", "simple_refactor", "formatting",
                "docstrings", "complex_code"]
    if "reasoning" in capability:
        return ["math_proof", "chain_of_thought", "debugging_logic",
                "algorithm_design"]
    return ["boilerplate", "simple_refactor", "formatting", "docstrings"]


@router.get("/{name}/status")
async def model_status(name: str) -> dict:
    from pvx.main import app_state

    if app_state is None:
        return {"status": "unknown"}

    # Check actual Ollama state rather than relying on PvX's potentially stale tracking
    actually_loaded = app_state.vram.get_actually_loaded_models()
    loaded = app_state.vram.get_loaded_model()

    is_loaded = (name in actually_loaded) or (loaded == name)
    vram_actual = actually_loaded.get(name, 0)
    vram_estimated = app_state.vram.MODEL_VRAM_MB.get(name, 0)

    return {
        "model": name,
        "status": "loaded" if is_loaded else "unloaded",
        "vram_mb_estimated": vram_estimated,
        "vram_mb_actual": vram_actual,
    }


@router.post("/load")
async def load_model(name: str) -> dict:
    """
    Pre-warm a model in Ollama VRAM.

    Sends a minimal generation request to Ollama with keep_alive=300 so the
    model is resident before the first real task arrives. Returns immediately
    after the warmup ping; actual load time depends on model size.
    """
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started"}

    if not app_state.vram.can_load(name):
        logger.warning("load_model_insufficient_vram", model=name)
        return {"error": "INSUFFICIENT_VRAM", "model": name}

    try:
        import ollama as _ollama
        # Warmup ping — loads the model and keeps it alive for 5 minutes
        _ollama.generate(model=name, prompt="", keep_alive=300)
        app_state.vram.load_model(name)
        logger.info("model_warmed_up_via_api", model=name)
        return {"status": "loaded", "model": name}
    except Exception as exc:
        logger.error("model_load_failed", model=name, error=str(exc))
        return {"error": str(exc), "model": name}


@router.post("/unload")
async def unload_model(name: str) -> dict:
    """
    Evict a model from VRAM via the Ollama keep_alive API.

    Uses keep_alive=0 to signal Ollama to release the model weights.
    The Ollama server stays running — only the model weights are freed.
    """
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started"}

    app_state.vram.unload_model(name)
    # Also clear PvX's tracked state if this is the current model
    if app_state.current_ollama_model == name:
        app_state.current_ollama_model = None

    logger.info("model_unloaded_via_api", model=name)
    return {"status": "unloaded", "model": name}
