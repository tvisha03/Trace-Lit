
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    SessionCreate,
    SessionRename,
    SessionResponse,
    SessionListResponse,
    WebSocketURLResponse,
)
from app.dependencies import get_db, get_faiss_store
from infrastructure.storage.file_storage import FileStorage
from services import session_service

router = APIRouter()

@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
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
    client_host = request.url.hostname or "localhost"
    client_port = request.url.port or 8000
    scheme = "wss" if request.url.scheme == "https" else "ws"

    ws_url = f"{scheme}://{client_host}:{client_port}/api/v1/ws/{session_id}"

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
    await session_service.delete_full_session(db, session_id, faiss_store, file_storage)
