"""
WebSocket endpoint — real-time paper processing progress updates.
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per session."""

    def __init__(self):
        # session_id → set of active WebSocket connections
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
        """Broadcast progress update to all connections in a session."""
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
        """Send an arbitrary event to all connections in a session."""
        message = json.dumps({"type": event_type, **data})
        conns = self._connections.get(session_id, set()).copy()
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws, session_id)


# Global singleton — imported by the paper worker
ws_manager = ConnectionManager()


@router.websocket("/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time progress updates.

    The client connects and receives JSON messages:
    - {"type": "paper_progress", "paper_id": "...", "progress": 0.5}
    - {"type": "paper_completed", "paper_id": "..."}
    - {"type": "paper_failed", "paper_id": "...", "error": "..."}
    """
    await ws_manager.connect(websocket, session_id)
    try:
        # Keep connection alive — client can send pings or messages
        while True:
            data = await websocket.receive_text()
            # Echo back as heartbeat acknowledgment
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
