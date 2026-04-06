import uuid
from datetime import datetime
from typing import List, Optional

from sqlmodel import SQLModel, Field, select
from sqlalchemy.ext.asyncio import AsyncSession

from pvx.store.database import write_queue, async_session_maker


# ── SQLModel table definitions ────────────────────────────────────────────────

class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project: str
    created_at: datetime
    metadata_json: str = ""


class MessageRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str
    model: str
    role: str
    content: str
    token_count: int
    timestamp: datetime


class EventRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str
    from_model: str
    to_model: str
    type: str
    payload: str  # JSON string
    timestamp: datetime


class TaskRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str
    model: str
    status: str
    priority: int
    depends_on: str  # JSON string list
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


# ── ConversationStore — CRUD through the WAL write queue ─────────────────────

class ConversationStore:
    """
    All writes go through the async write queue (single writer).
    Reads use a fresh session — WAL mode allows concurrent reads.
    """

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, project: str = "", metadata: str = "") -> Session:
        session = Session(
            id=f"sess_{uuid.uuid4().hex[:12]}",
            project=project,
            created_at=datetime.now(),
            metadata_json=metadata,
        )

        async def _write(db: AsyncSession) -> None:
            db.add(session)

        await write_queue.enqueue(_write)
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        async with async_session_maker() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def list_sessions(self) -> List[Session]:
        async with async_session_maker() as db:
            result = await db.execute(select(Session).order_by(Session.created_at.desc()))
            return result.scalars().all()

    async def delete_session(self, session_id: str) -> None:
        async def _write(db: AsyncSession) -> None:
            result = await db.execute(select(Session).where(Session.id == session_id))
            row = result.scalar_one_or_none()
            if row:
                await db.delete(row)

        await write_queue.enqueue(_write)

    # ── Messages ──────────────────────────────────────────────────────────────

    async def add_message(self, session_id: str, model: str, role: str,
                          content: str, token_count: int = 0) -> MessageRecord:
        record = MessageRecord(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            model=model,
            role=role,
            content=content,
            token_count=token_count,
            timestamp=datetime.now(),
        )

        async def _write(db: AsyncSession) -> None:
            db.add(record)

        await write_queue.enqueue(_write)
        return record

    async def get_messages(self, session_id: str) -> List[MessageRecord]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(MessageRecord)
                .where(MessageRecord.session_id == session_id)
                .order_by(MessageRecord.timestamp)
            )
            return result.scalars().all()

    # ── Tasks ─────────────────────────────────────────────────────────────────

    async def upsert_task(self, task_record: TaskRecord) -> None:
        async def _write(db: AsyncSession) -> None:
            existing = await db.get(TaskRecord, task_record.id)
            if existing:
                for field in ("status", "started_at", "completed_at", "error"):
                    setattr(existing, field, getattr(task_record, field))
            else:
                db.add(task_record)

        await write_queue.enqueue(_write)

    async def get_tasks(self, session_id: str) -> List[TaskRecord]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(TaskRecord).where(TaskRecord.session_id == session_id)
            )
            return result.scalars().all()

    # ── Events ────────────────────────────────────────────────────────────────

    async def get_events(self, session_id: str) -> List[EventRecord]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(EventRecord)
                .where(EventRecord.session_id == session_id)
                .order_by(EventRecord.timestamp)
            )
            return result.scalars().all()


conversation_store = ConversationStore()
