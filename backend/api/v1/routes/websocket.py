
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

class ConnectionManager:
    """Manages WebSocket connections keyed by (session_id, connection_id).

    Paper-processing progress is broadcast to every connection in a session
    (all browser tabs should see the update).  Targeted events can be sent
    to a specific connection_id for per-tab notifications such as export
    readiness.
    """

    def __init__(self):
        # session_id → {connection_id → WebSocket}
        self._connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(
        self, websocket: WebSocket, session_id: str, connection_id: str
    ) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, {})[connection_id] = websocket
        logger.info(f"WS connected: session={session_id} conn={connection_id}")

    async def disconnect(
        self, websocket: WebSocket, session_id: str, connection_id: Optional[str] = None
    ) -> None:
        session_conns = self._connections.get(session_id, {})
        if connection_id and connection_id in session_conns:
            session_conns.pop(connection_id, None)
        else:
            # Fall back to linear scan when connection_id is unknown.
            stale = [cid for cid, ws in session_conns.items() if ws is websocket]
            for cid in stale:
                session_conns.pop(cid, None)
        if not session_conns:
            self._connections.pop(session_id, None)
        logger.info(f"WS disconnected: session={session_id} conn={connection_id}")

    async def send_progress(
        self, session_id: str, paper_id: str, progress: float
    ) -> None:
        """Broadcast paper-processing progress to all connections in a session."""
        message = json.dumps({
            "type": "paper_progress",
            "paper_id": paper_id,
            "progress": progress,
        })
        await self._broadcast(session_id, message)

    async def send_event(
        self, session_id: str, event_type: str, data: dict
    ) -> None:
        """Broadcast a structured event to all connections in a session."""
        message = json.dumps({"type": event_type, **data})
        await self._broadcast(session_id, message)

    async def send_to_client(
        self, session_id: str, connection_id: str, event_type: str, data: dict
    ) -> None:
        """Send an event to a single specific connection (e.g. export ready)."""
        session_conns = self._connections.get(session_id, {})
        ws = session_conns.get(connection_id)
        if ws is None:
            logger.warning(
                f"send_to_client: no connection {connection_id} in session {session_id}"
            )
            return
        message = json.dumps({"type": event_type, **data})
        try:
            await ws.send_text(message)
        except Exception:
            await self.disconnect(ws, session_id, connection_id)

    async def _broadcast(self, session_id: str, message: str) -> None:
        """Send a raw message to every WebSocket in a session."""
        conns = dict(self._connections.get(session_id, {}))
        for connection_id, ws in conns.items():
            try:
                await ws.send_text(message)
            except Exception:
                await self.disconnect(ws, session_id, connection_id)

ws_manager = ConnectionManager()

@router.websocket("/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # Each browser tab/device generates a unique connection_id so the server
    # can send targeted messages when needed while still broadcasting shared
    # events (e.g. paper progress) to all connections in the session.
    connection_id = str(uuid.uuid4())
    await ws_manager.connect(websocket, session_id, connection_id)

    # Immediately send the assigned connection_id so the client can include
    # it in subsequent requests that require targeted server pushes.
    await websocket.send_text(
        json.dumps({"type": "connected", "connection_id": connection_id})
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        # Use the known connection_id for O(1) removal rather than a linear scan.
        await ws_manager.disconnect(websocket, session_id, connection_id)
