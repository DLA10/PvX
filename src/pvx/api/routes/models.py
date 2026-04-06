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

    # Return all models registered in the VRAM table (includes discovered models)
    # rather than only config.models.local, which would miss auto-discovered ones.
    local = list(app_state.vram.MODEL_VRAM_MB.keys())
    result = [m for m in local if m != "claude"] + ["claude"]
    return result


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
