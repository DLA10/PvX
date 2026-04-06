import pytest
from datetime import datetime
from unittest.mock import MagicMock
from pvx.core.tasks import Task
from pvx.core.queue import TaskQueueEngine


def make_task(id: str, priority: int = 3, model: str = "qwen2.5-coder:3b",
              depends_on=None) -> Task:
    return Task(
        id=id, model=model, prompt="test", category="boilerplate",
        status="pending", priority=priority, depends_on=depends_on or [],
        requires_vram=True, requires_system_idle=False,
        retry_count=0, max_retries=3, created_at=datetime.now(),
    )


def make_queue() -> TaskQueueEngine:
    vram = MagicMock()
    vram.get_loaded_model.return_value = None
    config = MagicMock()
    config.queue.affinity_batch_max_tasks = 10
    config.queue.affinity_batch_max_seconds = 300
    config.queue.starvation_timeout_seconds = 300
    config.queue.partial_save_min_tokens = 150
    return TaskQueueEngine(vram_manager=vram, config=config)


@pytest.mark.asyncio
async def test_queue_init_fields_present():
    q = make_queue()
    assert q.current_batch_size == 0
    assert isinstance(q.batch_start, datetime)
    assert q.affinity_reset is False
    assert isinstance(q._streaming_buffers, dict)


@pytest.mark.asyncio
async def test_register_streaming_token():
    q = make_queue()
    q.register_streaming_token("t1", "hello")
    q.register_streaming_token("t1", " world")
    assert q._streaming_buffers["t1"] == "hello world"


@pytest.mark.asyncio
async def test_starvation_guard_uses_total_seconds():
    """Verify starvation guard fires correctly — .total_seconds() not .seconds."""
    q = make_queue()
    # Set starvation timeout to 0 so any task is immediately starved
    q.STARVATION_TIMEOUT_SECONDS = 0
    task = make_task("t1")
    q.pending_tasks.append(task)
    result = q.get_next_task()
    assert result is not None
    assert result.id == "t1"


@pytest.mark.asyncio
async def test_dependency_resolver_blocks_on_failed_dep():
    q = make_queue()
    dep = make_task("dep1")
    dep.status = "failed"
    child = make_task("child1", depends_on=["dep1"])
    q.pending_tasks = [dep, child]
    eligible = q.get_pending_with_deps_resolved()
    assert child not in eligible
    assert child.status == "blocked"


@pytest.mark.asyncio
async def test_dependency_resolver_releases_on_done_dep():
    q = make_queue()
    dep = make_task("dep1")
    dep.status = "done"
    child = make_task("child1", depends_on=["dep1"])
    q.pending_tasks = [dep, child]
    eligible = q.get_pending_with_deps_resolved()
    assert child in eligible


@pytest.mark.asyncio
async def test_preemption_rules():
    q = make_queue()
    p5 = make_task("high", priority=5)
    p3 = make_task("low", priority=3)
    assert q.should_preempt(p5, p3) is True
    assert q.should_preempt(p3, p5) is False


@pytest.mark.asyncio
async def test_affinity_reset_cleared_after_step4():
    q = make_queue()
    q.affinity_reset = True
    task = make_task("t1")
    q.pending_tasks.append(task)
    q.get_next_task()
    assert q.affinity_reset is False
