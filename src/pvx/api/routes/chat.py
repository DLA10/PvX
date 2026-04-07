import asyncio
import json
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = structlog.get_logger()


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    prompt: str
    history: List[ChatMessage] = []


@router.get("/models")
async def list_chat_models() -> list:
    """Return models available for direct chat (Ollama models only)."""
    from pvx.main import app_state

    if app_state is None:
        return []

    return [
        name for name in app_state.vram.MODEL_VRAM_MB
        if name != "claude"
    ]


@router.post("/{model_name}/stream")
async def stream_chat(model_name: str, body: ChatRequest) -> StreamingResponse:
    """
    Stream a direct chat response from a specific Ollama model via SSE.

    Bypasses the task queue — intended for interactive use.
    The model must be in the VRAM table (discovered or config-registered).
    """
    from pvx.main import app_state

    if app_state is None:
        raise HTTPException(status_code=503, detail="PvX not started")

    if model_name not in app_state.vram.MODEL_VRAM_MB:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not registered")

    from pvx.models.base import Message

    async def event_generator():
        history = [Message(role=m.role, content=m.content) for m in body.history]

        # Run sync Ollama generate in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        token_queue: asyncio.Queue = asyncio.Queue()
        done_event = asyncio.Event()

        def _run_generate():
            """Sync worker — streams tokens into the async queue."""
            import ollama as _ollama
            messages = [{"role": m.role, "content": m.content} for m in history]
            messages.append({"role": "user", "content": body.prompt})
            try:
                stream = _ollama.chat(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    keep_alive=300,
                    options={"num_predict": 4096, "num_ctx": 8192, "temperature": 0.2},
                )
                for chunk in stream:
                    token = chunk.message.content or ""
                    if token:
                        loop.call_soon_threadsafe(token_queue.put_nowait, token)
            except Exception as exc:
                loop.call_soon_threadsafe(
                    token_queue.put_nowait,
                    json.dumps({"error": str(exc)})
                )
            finally:
                loop.call_soon_threadsafe(done_event.set)

        # Start generator in background thread
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop.run_in_executor(executor, _run_generate)

        # Stream tokens to client as SSE
        while not done_event.is_set() or not token_queue.empty():
            try:
                token = await asyncio.wait_for(token_queue.get(), timeout=0.1)
                yield f"data: {json.dumps({'token': token})}\n\n"
            except asyncio.TimeoutError:
                continue

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
