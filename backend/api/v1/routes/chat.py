from dataclasses import asdict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    ChatRequest,
    ChatResponse,
    VerificationItem,
    MessageListResponse,
    MessageResponse,
    SuggestedQuestionsResponse,
)
from app.dependencies import get_db, get_faiss_store
from infrastructure.llm.fallback_chain import FallbackChain
from services.chat_service import chat, chat_stream, get_suggested_questions
from infrastructure.db.crud.message_crud import get_messages_by_session, count_messages_by_session
from shared.errors import TraceLitError
from shared.utils.rate_limiter import SlidingWindowRateLimiter
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

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
    _chat_limiter.enforce(request)
    llm = _get_llm(request)
    try:
        response = await chat(session_id, body.query, db, faiss_store, llm, keywords=body.keywords)
    except TraceLitError:
        raise
    except Exception as exc:
        logger.error(f"Chat failed for session {session_id}: {exc}", exc_info=True)
        error_detail = f"{type(exc).__name__}: {str(exc)}" if str(exc) else type(exc).__name__
        raise TraceLitError(
            message=f"An error occurred while processing your request: {error_detail}. Please try again.",
            status_code=500,
        )

    # ===== TRANSFORMATION TYPE CLASSIFICATION =====
    # After HAVF verification, classify how each claim relates to its source
    # This helps researchers understand the reliability of each attributed claim
    # - Direct Quotes can be cited immediately
    # - Paraphrases need wording verification
    # - Syntheses require checking all sources
    # - Inferences must be independently verified before citation
    # ==============================================
    if response.havf_results:
        from domain.verification.transformation_classifier import classify_transformations
        response.havf_results = await classify_transformations(response.havf_results)

    return ChatResponse(
        content=response.content,
        provider=response.provider.value,
        havf_results=[
            VerificationItem(**(r if isinstance(r, dict) else asdict(r))) for r in response.havf_results
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
    _chat_limiter.enforce(request)
    llm = _get_llm(request)
    generator = await chat_stream(session_id, body.query, db, faiss_store, llm, keywords=body.keywords)
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
    limit: int | None = None,
    offset: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    messages = await get_messages_by_session(
        db, session_id, limit=limit, offset=offset,
    )
    total = await count_messages_by_session(db, session_id)
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
    return MessageListResponse(
        messages=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/suggested-questions", response_model=SuggestedQuestionsResponse)
async def suggested_questions(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    llm = _get_llm(request)
    questions = await get_suggested_questions(session_id, db, llm)
    return SuggestedQuestionsResponse(
        session_id=session_id,
        questions=questions,
    )

