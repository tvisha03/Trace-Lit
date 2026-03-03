
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    ChatRequest,
    ChatResponse,
    VerificationItem,
    MessageListResponse,
    MessageResponse,
)
from app.dependencies import get_db, get_faiss_store
from infrastructure.llm.fallback_chain import FallbackChain
from services.chat_service import chat, chat_stream
from infrastructure.db.crud.message_crud import get_messages_by_session
from shared.errors import NotFoundError, InsufficientDataError, TraceLitError
from shared.utils.rate_limiter import SlidingWindowRateLimiter
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# CRT-003/MED-004: Chat calls the LLM + HAVF verification pipeline which is
# both expensive and quota-limited.  Cap each client IP to 15 requests/min to
# prevent accidental DoS or rapid API-quota exhaustion.
_chat_limiter = SlidingWindowRateLimiter(
    max_calls=15, window_seconds=60.0, resource_name="chat requests",
)

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.post("", response_model=ChatResponse)
async def send_message(
    session_id: str,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    """Non-streaming chat endpoint. Returns a fully-formed ChatResponse."""
    _chat_limiter.enforce(request)
    llm = _get_llm(request)
    try:
        response = await chat(session_id, body.query, db, faiss_store, llm)
    except TraceLitError:
        # TraceLitError subclasses (NotFoundError, InsufficientDataError, etc.)
        # are handled by the global exception handler in app/exceptions.py.
        raise
    except Exception as exc:
        # Catch-all for LLM failures, FAISS errors, and unexpected exceptions.
        # Log full details server-side; return a safe, generic message to the
        # client so no internal state is leaked (MINOR-002 fix).
        logger.error(f"Chat failed for session {session_id}: {exc}", exc_info=True)
        raise TraceLitError(
            message="An error occurred while processing your request. Please try again.",
            status_code=500,
        )
    return ChatResponse(
        content=response.content,
        provider=response.provider.value,
        havf_results=[
            VerificationItem(
                claim=r.claim,
                confidence=r.confidence.value,
                score=r.score,
                source_sentence=r.source_sentence,
                paragraph_id=r.paragraph_id,
                sentence_key=r.sentence_key,
            )
            for r in response.havf_results
        ],
        token_count=response.token_count,
        latency_ms=response.latency_ms,
    )

@router.post("/stream", response_class=StreamingResponse)
async def send_message_stream(
    session_id: str,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    """Streaming chat endpoint using Server-Sent Events (SSE).

    The response body is a stream of ``data: <json>\\n\\n`` lines.  Each line
    carries a JSON object with a ``type`` field that determines its shape:

    - ``query_type``  → SSEQueryTypeEvent
    - ``sources``     → list[SSESourceItem]
    - ``token``       → SSETokenEvent  (one per LLM token)
    - ``havf``        → SSEHavfEvent   (after all tokens)
    - ``done``        → SSEDoneEvent
    - ``error``       → SSEErrorEvent

    See ``api/v1/schemas.py`` for the Pydantic shapes of each event type.
    """
    _chat_limiter.enforce(request)
    llm = _get_llm(request)
    generator = await chat_stream(session_id, body.query, db, faiss_store, llm)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    messages = await get_messages_by_session(db, session_id)
    items = [
        MessageResponse(
            id=str(m.id),
            role=m.role.value if hasattr(m.role, "value") else m.role,
            content=m.content,
            provider=m.provider,
            havf_results=[
                VerificationItem(**r) for r in (m.havf_results or [])
            ] if m.havf_results else None,
            token_count=m.token_count,
            latency_ms=m.latency_ms,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]
    return MessageListResponse(messages=items)
