"""TraceLit — WebSocket endpoint for paper processing progress.

Broadcasts real-time progress updates to connected clients during
paper upload and processing. Each client receives updates for all
active papers in their session.
"""

import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger


router = APIRouter()


# ============================================================
# Connection Manager
# ============================================================

class ConnectionManager:
    """Manages active WebSocket connections for progress broadcasting."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("WebSocket client connected (total: {})", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("WebSocket client disconnected (total: {})", len(self._connections))

    async def broadcast(self, message: Dict) -> None:
        """Broadcast a JSON message to all connected clients."""
        if not self._connections:
            return

        payload = json.dumps(message)
        disconnected = set()

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.add(ws)

            for ws in disconnected:
                self._connections.discard(ws)

    async def send_to(self, websocket: WebSocket, message: Dict) -> None:
        """Send a JSON message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            pass

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# ============================================================
# Singleton Manager
# ============================================================

_manager: ConnectionManager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    return _manager


# ============================================================
# Progress Callback for Paper Worker
# ============================================================

async def paper_progress_callback(
    paper_id: str,
    stage: str,
    progress: float,
    error: str = None,
) -> None:
    """Callback invoked by SmartPaperQueue to broadcast progress updates."""
    stage_value = stage.value if hasattr(stage, "value") else str(stage)
    message = {
        "type": "paper_progress",
        "paper_id": paper_id,
        "stage": stage_value,
        "progress": round(progress, 2),
    }
    if error:
        message["error"] = error

    await _manager.broadcast(message)


# ============================================================
# WebSocket Endpoint
# ============================================================

@router.websocket("/ws/papers/progress")
async def paper_progress_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time paper processing updates.

    Clients connect here to receive progress notifications for all
    active paper processing jobs. Messages are JSON:

    {
        "type": "paper_progress",
        "paper_id": "abc123",
        "stage": "extracting" | "chunking" | "embedding" | "indexing" | "complete" | "failed",
        "progress": 0.0 - 1.0,
        "error": null | "error message"
    }
    """
    await _manager.connect(websocket)

    try:
        # Send initial status of all active jobs
        from workers.paper_worker import get_paper_queue
        queue = get_paper_queue()
        statuses = queue.get_all_statuses()
        if statuses:
            await _manager.send_to(websocket, {
                "type": "initial_status",
                "jobs": statuses,
            })

        # Keep connection alive; handle incoming messages (e.g., pings)
        while True:
            try:
                data = await websocket.receive_text()
                # Handle client pings
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await _manager.send_to(websocket, {"type": "pong"})
                elif msg.get("type") == "status":
                    # On-demand status request
                    statuses = queue.get_all_statuses()
                    await _manager.send_to(websocket, {
                        "type": "status_update",
                        "jobs": statuses,
                    })
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error: {}", exc)
    finally:
        await _manager.disconnect(websocket)
