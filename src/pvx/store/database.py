import asyncio
from typing import Optional, Callable, Any
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

DATABASE_URL = "sqlite+aiosqlite:///pvx.db"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

# Enable WAL mode for all connections
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

class WriteQueue:
    """
    Serializes SQLite writes to prevent WAL contention under high concurrency.
    """
    def __init__(self):
        self.queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, operation: Callable, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((operation, args, future))
        return await future

    async def _worker(self):
        while True:
            try:
                operation, args, future = await self.queue.get()
                
                try:
                    async with async_session_maker() as session:
                        result = await operation(session, *args)
                        await session.commit()
                        if not future.done():
                            future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error
                pass

write_queue = WriteQueue()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
