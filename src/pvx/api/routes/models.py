from fastapi import APIRouter
import structlog

router = APIRouter(prefix="/api/models", tags=["models"])
logger = structlog.get_logger()


@router.get("/")
async def list_models() -> list:
    """List all model names known to PvX."""
    from pvx.main import app_state

    if app_state is None:
        return []

    return list(app_state.vram.MODEL_VRAM_MB.keys())


@router.get("/available")
async def list_available_models() -> dict:
    """
    Return every installed Ollama model with VRAM info and current load status.

    This is the primary tool Claude Code calls at session start to see what is
    installed on this machine. Claude Code and the user then decide together
    which model to use for which tasks — PvX makes no recommendations.

    Fields per model:
    - name: exact Ollama model identifier to pass to submit_task(model=...)
    - size_gb: disk size in GB (read the name — it tells you what it is)
    - vram_required_mb: estimated VRAM needed to load this model
    - can_load_now: whether free VRAM is sufficient right now
    - currently_loaded: whether this model is already resident in VRAM
    - status: "loaded" | "available" | "too_large"
    """
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started", "models": []}

    vram_state      = app_state.vram.poll()
    actually_loaded = app_state.vram.get_actually_loaded_models()

    models = []
    for name, vram_mb in app_state.vram.MODEL_VRAM_MB.items():
        is_loaded = name in actually_loaded or app_state.vram.loaded_model == name
        can_load  = app_state.vram.can_load(name)

        models.append({
            "name":             name,
            "size_gb":          getattr(app_state, "_discovery_size_gb", {}).get(name),
            "vram_required_mb": vram_mb,
            "can_load_now":     can_load,
            "currently_loaded": is_loaded,
            "status":           "loaded" if is_loaded else ("available" if can_load else "too_large"),
        })

    _order = {"loaded": 0, "available": 1, "too_large": 2}
    models.sort(key=lambda m: _order.get(m["status"], 9))

    return {
        "models": models,
        "gpu": {
            "total_mb":            vram_state.total_mb,
            "used_mb":             vram_state.used_mb,
            "free_mb":             vram_state.free_mb,
            "gpu_utilisation_pct": vram_state.gpu_utilisation_pct,
        },
        "note": (
            "One Ollama model in VRAM at a time on this GPU. "
            "Switching models takes 5–15 s cold-start. "
            "PvX batches same-model tasks to minimise swaps."
        ),
    }


@router.get("/{name}/status")
async def model_status(name: str) -> dict:
    from pvx.main import app_state

    if app_state is None:
        return {"status": "unknown"}

    actually_loaded = app_state.vram.get_actually_loaded_models()
    loaded          = app_state.vram.get_loaded_model()
    is_loaded       = (name in actually_loaded) or (loaded == name)

    return {
        "model":              name,
        "status":             "loaded" if is_loaded else "unloaded",
        "vram_mb_estimated":  app_state.vram.MODEL_VRAM_MB.get(name, 0),
        "vram_mb_actual":     actually_loaded.get(name, 0),
    }


@router.post("/load")
async def load_model(name: str) -> dict:
    """Pre-warm a model in Ollama VRAM before the first task arrives."""
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started"}

    if not app_state.vram.can_load(name):
        logger.warning("load_model_insufficient_vram", model=name)
        return {"error": "INSUFFICIENT_VRAM", "model": name}

    try:
        import ollama as _ollama
        _ollama.generate(model=name, prompt="", keep_alive=300)
        app_state.vram.load_model(name)
        logger.info("model_warmed_up", model=name)
        return {"status": "loaded", "model": name}
    except Exception as exc:
        logger.error("model_load_failed", model=name, error=str(exc))
        return {"error": str(exc), "model": name}


@router.post("/unload")
async def unload_model(name: str) -> dict:
    """Evict a model from VRAM via the Ollama keep_alive=0 API."""
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started"}

    app_state.vram.unload_model(name)
    if app_state.current_ollama_model == name:
        app_state.current_ollama_model = None

    logger.info("model_unloaded", model=name)
    return {"status": "unloaded", "model": name}
