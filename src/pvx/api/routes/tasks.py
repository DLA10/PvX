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
    model: str                   # Required — Claude Code specifies the model explicitly
    priority: int = 3
    category: Optional[str] = None   # Optional label for display only
    depends_on: List[str] = []


@router.post("/")
async def submit_task(task_in: TaskSubmit) -> dict:
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    # Validate the model is known (or is "claude")
    if task_in.model != "claude" and task_in.model not in app_state.vram.MODEL_VRAM_MB:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown model '{task_in.model}'. "
                "Call list_available_models() to see what is installed."
            ),
        )

    task = Task(
        id=f"task_{uuid.uuid4().hex[:12]}",
        model=task_in.model,
        prompt=task_in.prompt,
        category=task_in.category or "",
        status="pending",
        priority=max(1, min(5, task_in.priority)),
        depends_on=task_in.depends_on,
        requires_vram=task_in.model != "claude",
        requires_system_idle=False,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(),
    )
    app_state.queue.pending_tasks.append(task)
    logger.info("task_submitted", task_id=task.id, model=task.model,
                priority=task.priority, category=task.category)
    return {"task_id": task.id, "status": task.status, "model": task.model,
            "category": task.category}


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
    logger.info("task_cancelled", task_id=task_id)
    return {"task_id": task_id, "status": "cancelled"}
