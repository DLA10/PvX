import uuid
import json
from typing import Any, Dict, List, Callable
from dataclasses import dataclass
from datetime import datetime

import structlog

log = structlog.get_logger()


@dataclass
class Event:
    id: str
    type: str
    payload: Any
    timestamp: datetime
    session_id: str = ""
    task_id: str = ""
    from_model: str = ""
    to_model: str = ""


class EventBus:
    """
    In-memory pub/sub with SQLite persistence via the write queue.

    Subscribers are in-memory only — cleared on restart (v0.1 by design).
    All events are persisted to SQLite for session replay via GET /api/sessions/{id}.
    Automatic replay on reconnect is a v0.2 feature.
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self._write_queue = None  # Injected after database init to avoid circular import

    def set_write_queue(self, write_queue: Any) -> None:
        """Wire up the database write queue after startup."""
        self._write_queue = write_queue

    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def emit(self, event_type: str, payload: Any,
             session_id: str = "", task_id: str = "",
             from_model: str = "", to_model: str = "") -> Event:
        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            type=event_type,
            payload=payload,
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
            from_model=from_model,
            to_model=to_model,
        )

        # Notify in-memory subscribers
        for callback in self.subscribers.get(event_type, []):
            try:
                callback(event)
            except Exception as e:
                log.error("event_subscriber_error", event_type=event_type, error=str(e))

        # Persist to SQLite via write queue
        if self._write_queue is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._persist(event))
            except RuntimeError:
                pass  # No running loop (e.g. in tests) — skip persistence

        return event

    async def _persist(self, event: Event) -> None:
        """Write event to SQLite through the serialised write queue."""
        from pvx.store.database import write_queue  # local import avoids circular

        async def _write(session: Any) -> None:
            from pvx.store.models import EventRecord
            record = EventRecord(
                id=event.id,
                session_id=event.session_id,
                from_model=event.from_model,
                to_model=event.to_model,
                type=event.type,
                payload=json.dumps(event.payload, default=str),
                timestamp=event.timestamp,
            )
            session.add(record)

        await write_queue.enqueue(_write)


event_bus = EventBus()
