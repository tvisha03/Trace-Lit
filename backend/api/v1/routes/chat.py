"""
Chat routes — query with RAG + HAVF verification.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ChatRequest, ChatResponse, VerificationItem, MessageListResponse, MessageResponse
from app.dependencies import get_db, get_faiss_store
from infrastructure.llm.fallback_chain import FallbackChain
from services.chat_service import chat, chat_stream
from infrastructure.db.crud.message_crud import get_messages_by_session

router = APIRouter()


def _get_llm(request: Request) -> FallbackChain:
    """Retrieve the shared LLM fallback chain from app state."""
    return request.app.state.llm


@router.post("", response_model=ChatResponse)
async def send_message(
    session_id: str,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    """
    Send a query and receive a verified response.
    If stream=True, returns an SSE stream instead.
    """
    llm = _get_llm(request)

    if body.stream:
        generator = await chat_stream(session_id, body.query, db, faiss_store, llm)
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    response = await chat(session_id, body.query, db, faiss_store, llm)

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


@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a session's chat history."""
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
