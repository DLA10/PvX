import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pvx.core.tasks import Task
import structlog

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = structlog.get_logger()


class TaskSubmit(BaseModel):
    prompt: str
    # Priority: 5 = critical/urgent (preempts running tasks)
    #           4 = high
    #           3 = normal (default)
    #           2 = low
    #           1 = background (never preempts)
    priority: int = 3
    model: Optional[str] = None
    category: Optional[str] = None
    depends_on: List[str] = []


@router.post("/")
async def submit_task(task_in: TaskSubmit) -> dict:
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    # Classify the prompt when no category is explicitly provided.
    # This runs the full keyword → cache → Claude escalation chain so
    # tasks are routed to the right model rather than always defaulting
    # to "complex_code".
    if task_in.category:
        category = task_in.category
    else:
        classification = app_state.classifier.classify(task_in.prompt)
        category = classification.category
        logger.debug("task_classified",
                     category=category,
                     confidence=classification.confidence,
                     classified_by=classification.classified_by)

    tmp_for_routing = Task(
        id="tmp",
        model="",
        prompt=task_in.prompt,
        category=category,
        status="pending",
        priority=task_in.priority,
        depends_on=[],
        requires_vram=True,
        requires_system_idle=False,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(),
    )
    routed_model: str = task_in.model or app_state.router.route(tmp_for_routing)

    task = Task(
        id=f"task_{uuid.uuid4().hex[:12]}",
        model=routed_model,
        prompt=task_in.prompt,
        category=category,
        status="pending",
        priority=task_in.priority,
        depends_on=task_in.depends_on,
        requires_vram=True,
        requires_system_idle=False,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(),
    )
    app_state.queue.pending_tasks.append(task)
    logger.info("task_submitted_via_api", task_id=task.id, priority=task.priority,
                category=category)
    return {"task_id": task.id, "status": task.status, "model": task.model,
            "category": category}


@router.get("/")
async def list_tasks() -> list:
    from pvx.main import app_state

    if app_state is None:
        return []

    return [
        {
            "id": t.id,
            "status": t.status,
            "model": t.model,
            "priority": t.priority,
            "created_at": t.created_at.isoformat(),
            "category": t.category,
        }
        for t in app_state.queue.pending_tasks
    ]


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    task = next((t for t in app_state.queue.pending_tasks if t.id == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "id": task.id,
        "status": task.status,
        "model": task.model,
        "priority": task.priority,
        "output": task.output,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> dict:
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    task = next((t for t in app_state.queue.pending_tasks if t.id == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("done", "failed"):
        raise HTTPException(status_code=400, detail=f"Task already {task.status}")

    task.status = "failed"
    task.error = "CANCELLED_BY_USER"
    logger.info("task_cancelled_via_api", task_id=task_id)
    return {"task_id": task_id, "status": "cancelled"}


@router.post("/analyze")
async def analyze_task(prompt: str) -> dict:
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    classification = app_state.classifier.classify(prompt)
    tmp_task = Task(
        id="tmp",
        model="",
        prompt=prompt,
        category=classification.category,
        status="pending",
        priority=3,
        depends_on=[],
        requires_vram=True,
        requires_system_idle=False,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(),
    )
    routed_model: str = app_state.router.route(tmp_task)
    vram_state = app_state.vram.poll()
    required_mb: int = app_state.vram.MODEL_VRAM_MB.get(routed_model, 0)

    return {
        "prompt": prompt,
        "classification": {
            "category": classification.category,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "classified_by": classification.classified_by,
        },
        "routing": {"model": routed_model},
        "vram": {
            "required_mb": required_mb,
            "free_mb": vram_state.free_mb,
            "sufficient": vram_state.free_mb >= required_mb,
        },
    }
