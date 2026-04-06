from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import json
from pvx.core.events import event_bus, Event
from pvx.api.routes.vram import router as vram_router
from pvx.api.routes.tasks import router as tasks_router
from pvx.api.routes.models import router as models_router
from pvx.api.routes.stream import router as stream_router

app = FastAPI(title="PvX Platform API", version="0.1.0")

app.include_router(vram_router)
app.include_router(tasks_router)
app.include_router(models_router)
# SSE streaming must be included AFTER tasks_router — both use /api/tasks prefix
# and FastAPI resolves routes in registration order.
app.include_router(stream_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/api/health")
async def health_check():
    from pvx.main import app_state
    return {
        "status": "live",
        "version": "0.1.0",
        "pvx_ready": app_state is not None,
    }

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def event_listener(event: Event):
    import asyncio
    payload = json.dumps({
        "type": event.type,
        "payload": event.payload,
        "timestamp": event.timestamp.isoformat(),
        "task_id": event.task_id
    })
    # Since event_bus.emit is synchronous, we use the event loop if available
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(payload))
    except Exception:
        pass

# Subscribe to all events for broadcasting
event_bus.subscribe("*", event_listener)
