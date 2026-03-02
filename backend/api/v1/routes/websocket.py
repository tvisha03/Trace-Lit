
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

class ConnectionManager:

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self._connections.setdefault(session_id, set()).add(websocket)
        logger.info(f"WS connected: session {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        conns = self._connections.get(session_id, set())
        conns.discard(websocket)
        if not conns:
            self._connections.pop(session_id, None)
        logger.info(f"WS disconnected: session {session_id}")

    async def send_progress(self, session_id: str, paper_id: str, progress: float):
        message = json.dumps({
            "type": "paper_progress",
            "paper_id": paper_id,
            "progress": progress,
        })
        conns = self._connections.get(session_id, set()).copy()
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws, session_id)

    async def send_event(self, session_id: str, event_type: str, data: dict):
        message = json.dumps({"type": event_type, **data})
        conns = self._connections.get(session_id, set()).copy()
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws, session_id)

ws_manager = ConnectionManager()

@router.websocket("/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
