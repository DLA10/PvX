import pytest
from unittest.mock import patch, MagicMock
from pvx.core.vram import VRAMManager, State, VRAMState


def make_vram_no_gpu() -> VRAMManager:
    """VRAMManager with pynvml disabled — safe for CI without GPU."""
    import pynvml
    with patch("pvx.core.vram.pynvml.nvmlInit", side_effect=pynvml.NVMLError(0)):
        v = VRAMManager()
    return v


@pytest.mark.asyncio
async def test_vram_init_state_is_idle():
    v = make_vram_no_gpu()
    assert v.state == State.IDLE
    assert v.loaded_model is None


@pytest.mark.asyncio
async def test_vram_load_model_sets_state():
    v = make_vram_no_gpu()
    v.load_model("qwen2.5-coder:3b")
    assert v.state == State.LOADED
    assert v.get_loaded_model() == "qwen2.5-coder:3b"


@pytest.mark.asyncio
async def test_vram_state_transitions():
    v = make_vram_no_gpu()
    v.load_model("deepseek-r1:7b")
    v.start_generation()
    assert v.state == State.RUNNING
    v.end_generation()
    assert v.state == State.LOADED


@pytest.mark.asyncio
async def test_zombie_detection_uses_total_seconds():
    """Verify zombie uses .total_seconds() not .seconds."""
    from datetime import datetime, timedelta
    v = make_vram_no_gpu()
    task = MagicMock()
    task.status = "running"
    task.started_at = datetime.now() - timedelta(seconds=90)
    state = VRAMState(total_mb=8192, used_mb=6000, free_mb=2192,
                      gpu_utilisation_pct=0, running_pids=[])
    assert v.detect_zombie(task, state) is True


@pytest.mark.asyncio
async def test_zombie_not_triggered_when_gpu_active():
    from datetime import datetime, timedelta
    v = make_vram_no_gpu()
    task = MagicMock()
    task.status = "running"
    task.started_at = datetime.now() - timedelta(seconds=90)
    state = VRAMState(total_mb=8192, used_mb=6000, free_mb=2192,
                      gpu_utilisation_pct=50, running_pids=[])
    assert v.detect_zombie(task, state) is False


@pytest.mark.asyncio
async def test_can_load_respects_safety_buffer():
    v = make_vram_no_gpu()
    with patch.object(v, "poll", return_value=VRAMState(
        total_mb=8192, used_mb=7000, free_mb=1192,
        gpu_utilisation_pct=0, running_pids=[]
    )):
        # 1192MB free, need 2000 + 512 buffer = 2512 → cannot load
        assert v.can_load("qwen2.5-coder:3b") is False
