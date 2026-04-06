"""
SSE streaming endpoint — exposes live token output for running tasks.

Clients connect to GET /api/tasks/{task_id}/stream and receive a text/event-stream
that emits incremental token deltas while the task is running, then a final
completion event when done. No polling required.
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/tasks", tags=["stream"])


@router.get("/{task_id}/stream")
async def stream_task_output(task_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream for a running task.

    Events emitted:
      • While running:   {"delta": "<new_chars>", "total_chars": N}
      • On completion:   {"done": true, "status": "done|failed|...", "output": "...", "error": "..."}
      • Task not found:  {"error": "task_not_found"}

    Usage (curl):
        curl -N http://localhost:8000/api/tasks/{task_id}/stream
    """

    async def event_generator():
        from pvx.main import app_state  # late import — avoids circular at module load

        if app_state is None:
            yield _sse({"error": "pvx_not_started"})
            return

        last_len = 0
        poll_interval = 0.1  # 100 ms — low latency, low CPU

        while True:
            task = next(
                (t for t in app_state.queue.pending_tasks if t.id == task_id),
                None,
            )
            if task is None:
                yield _sse({"error": "task_not_found", "task_id": task_id})
                return

            # Emit any new token characters accumulated since last poll
            partial = app_state.queue.get_current_output(task)
            if len(partial) > last_len:
                delta = partial[last_len:]
                last_len = len(partial)
                yield _sse({"delta": delta, "total_chars": last_len})

            # Terminal states — emit final event and close stream
            if task.status in ("done", "failed", "blocked", "timeout", "preempted"):
                yield _sse({
                    "done": True,
                    "status": task.status,
                    "output": task.output,
                    "error": task.error,
                    "model": task.model,
                })
                return

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


def _sse(payload: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"
