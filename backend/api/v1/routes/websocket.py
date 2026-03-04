
import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional
import time

from shared.constants import MAX_WS_CONNECTIONS_PER_SESSION
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_WS_HEARTBEAT_INTERVAL: float = 30.0

# FIXED MED-001: Cache session existence to avoid creating new DB connection on every WS connect
_session_cache: dict[str, tuple[bool, float]] = {}
_SESSION_CACHE_TTL: float = 60.0  # Cache for 60 seconds


async def _session_exists(session_id: str) -> bool:
    # Check cache first
    now = time.time()
    if session_id in _session_cache:
        cached_result, cached_time = _session_cache[session_id]
        if now - cached_time < _SESSION_CACHE_TTL:
            return cached_result

    try:
        from infrastructure.db.database import async_session_factory
        from infrastructure.db.crud.session_crud import get_session
        async with async_session_factory() as db:
            session = await get_session(db, session_id)
            result = session is not None
            # Update cache
            _session_cache[session_id] = (result, now)
            return result
    except Exception as exc:
        logger.warning(f"Session validation failed for WS {session_id}: {exc}")
        return False

class ConnectionManager:

    def __init__(self):
        self._connections: dict[str, dict[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, session_id: str, connection_id: str
    ) -> bool:
        async with self._lock:
            session_conns = self._connections.get(session_id, {})
            if len(session_conns) >= MAX_WS_CONNECTIONS_PER_SESSION:
                await websocket.close(
                    code=4029,
                    reason=f"Too many connections for session (max {MAX_WS_CONNECTIONS_PER_SESSION})",
                )
                logger.warning(
                    f"WS rejected: session {session_id} already has "
                    f"{len(session_conns)} connections (cap={MAX_WS_CONNECTIONS_PER_SESSION})"
                )
                return False
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, {})[connection_id] = websocket
        logger.info(f"WS connected: session={session_id} conn={connection_id}")
        return True

    async def disconnect(
        self, websocket: WebSocket, session_id: str, connection_id: Optional[str] = None
    ) -> None:
        async with self._lock:
            session_conns = self._connections.get(session_id, {})
            if connection_id and connection_id in session_conns:
                session_conns.pop(connection_id, None)
            else:
                stale = [cid for cid, ws in session_conns.items() if ws is websocket]
                for cid in stale:
                    session_conns.pop(cid, None)
            if not session_conns:
                self._connections.pop(session_id, None)
        logger.info(f"WS disconnected: session={session_id} conn={connection_id}")

    async def send_event(
        self, session_id: str, event_type: str, data: dict
    ) -> None:
        message = json.dumps({"type": event_type, **data})
        await self._broadcast(session_id, message)

    async def send_to_client(
        self, session_id: str, connection_id: str, event_type: str, data: dict
    ) -> None:
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
        async with self._lock:
            conns = dict(self._connections.get(session_id, {}))
        stale_ids: list[tuple[str, WebSocket]] = []
        for connection_id, ws in conns.items():
            try:
                await ws.send_text(message)
            except Exception:
                stale_ids.append((connection_id, ws))
        for connection_id, ws in stale_ids:
            await self.disconnect(ws, session_id, connection_id)

ws_manager = ConnectionManager()

@router.websocket("/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    if not await _session_exists(session_id):
        await websocket.close(code=4004, reason="Session not found")
        logger.warning(f"WS rejected: session {session_id} does not exist")
        return

    connection_id = str(uuid.uuid4())
    accepted = await ws_manager.connect(websocket, session_id, connection_id)
    if not accepted:
        return

    await websocket.send_text(
        json.dumps({"type": "connected", "connection_id": connection_id})
    )

    try:
        async def _heartbeat():
            try:
                while True:
                    await asyncio.sleep(_WS_HEARTBEAT_INTERVAL)
                    await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                pass

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        finally:
            heartbeat_task.cancel()
    finally:
        await ws_manager.disconnect(websocket, session_id, connection_id)

