from fastapi import APIRouter
import structlog

router = APIRouter(prefix="/api/vram", tags=["vram"])
logger = structlog.get_logger()


@router.get("/")
async def get_vram_state() -> dict:
    from pvx.main import app_state

    if app_state is None:
        return {"error": "PvX not started"}

    state = app_state.vram.poll()
    return {
        "total_mb": state.total_mb,
        "used_mb": state.used_mb,
        "free_mb": state.free_mb,
        "gpu_utilisation_pct": state.gpu_utilisation_pct,
        "vram_state": app_state.vram.state.value,
        "loaded_model": app_state.vram.get_loaded_model(),
    }


@router.get("/simple")
async def get_vram_simple() -> dict:
    from pvx.main import app_state

    if app_state is None:
        return {"used_pct": 0}

    state = app_state.vram.poll()
    if state.total_mb == 0:
        return {"used_pct": 0}

    return {"used_pct": round(state.used_mb / state.total_mb * 100, 1)}
