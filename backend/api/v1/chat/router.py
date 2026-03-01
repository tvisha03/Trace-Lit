"""TraceLit — v1 Chat Router.

Thin router: delegates all business logic to services.chat_service.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.v1.schemas import ChatQueryRequest, ChatResponse
from app.dependencies import get_db
from infrastructure.db.models.session import Session as SessionModel

router = APIRouter()


def _get_session_or_404(session_id: str, db: Session) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@router.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    request: ChatQueryRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a query and receive a cited response.

    Uses multi-provider LLM with automatic fallback.
    Returns sentence-level HAVF verification.
    """
    from services.chat_service import handle_chat_query

    session = _get_session_or_404(request.session_id, db)
    return await handle_chat_query(request=request, session=session, db=db)


@router.post("/chat/query/stream")
async def chat_query_stream(
    request: ChatQueryRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a cited response via Server-Sent Events.

    SSE event types:
    - ``{"type": "chunk", "text": "..."}`` — incremental text
    - ``{"type": "done", "metadata": {...}}`` — final verification metadata
    - ``{"type": "error", "message": "..."}`` — error condition
    """
    from services.chat_service import stream_chat_query

    session = _get_session_or_404(request.session_id, db)
    return StreamingResponse(
        stream_chat_query(request=request, session=session, db=db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
