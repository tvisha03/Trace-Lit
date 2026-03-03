
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    SessionCreate,
    SessionRename,
    SessionResponse,
    SessionListResponse,
    WebSocketURLResponse,
)
from api.v1.routes.websocket import ws_manager
from app.dependencies import get_db, get_faiss_store
from infrastructure.storage.file_storage import FileStorage
from services import session_service
from shared.constants import MAX_SESSIONS
from shared.errors import TraceLitError
from shared.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    # GAP-2: Enforce a maximum number of sessions to prevent unbounded
    # resource growth (DB rows, FAISS indexes, uploaded files).
    existing = await session_service.list_all_sessions(db)
    if len(existing) >= MAX_SESSIONS:
        raise TraceLitError(
            message=(
                f"Maximum session limit ({MAX_SESSIONS}) reached. "
                "Please delete an existing session before creating a new one."
            ),
            status_code=409,
        )

    result = await session_service.create_new_session(
        db, title=body.title, description=body.description
    )
    return result

@router.get("", response_model=SessionListResponse)
async def list_sessions(db: AsyncSession = Depends(get_db)):
    sessions = await session_service.list_all_sessions(db)
    return SessionListResponse(sessions=sessions)

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await session_service.get_session_detail(db, session_id)

@router.patch("/{session_id}", response_model=SessionResponse)
async def rename_session(
    session_id: str,
    body: SessionRename,
    db: AsyncSession = Depends(get_db),
):
    result = await session_service.update_session_title(db, session_id, body.title)
    return result

@router.get("/{session_id}/ws-url", response_model=WebSocketURLResponse)
async def get_websocket_url(
    session_id: str,
    request: Request,
):
    # Use request.url.netloc (host:port) so standard ports are omitted automatically
    # and reverse-proxy forwarded headers are respected transparently.
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{request.url.netloc}/ws/{session_id}"

    return WebSocketURLResponse(
        websocket_url=ws_url,
        session_id=session_id,
    )

@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    file_storage = FileStorage()
    deleted_paper_ids = await session_service.delete_full_session(
        db, session_id, faiss_store, file_storage
    )

    # Broadcast deletion events top-down: each paper first (in the order they
    # belonged to the session), then the session itself.  Events fire after the
    # DB commit so clients only see confirmed state changes.
    for paper_id in deleted_paper_ids:
        try:
            await ws_manager.send_event(
                session_id,
                "paper_deleted",
                {"paper_id": paper_id, "session_id": session_id},
            )
        except Exception as exc:
            logger.warning(f"WS paper_deleted event failed for {paper_id}: {exc}")

    try:
        await ws_manager.send_event(
            session_id,
            "session_deleted",
            {"session_id": session_id},
        )
    except Exception as exc:
        logger.warning(f"WS session_deleted event failed for {session_id}: {exc}")
