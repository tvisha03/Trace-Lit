from sqlalchemy.ext.asyncio import AsyncSession

from domain.generation.chat_engine import generate_response, ChatResponse
from domain.generation.streaming import stream_chat_response
from infrastructure.db.crud.message_crud import create_message, get_recent_messages
from infrastructure.db.crud.paper_crud import get_papers_by_session
from infrastructure.db.crud.session_crud import get_session
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.enums import PaperStatus, MessageRole
from shared.errors import NotFoundError
from shared.logger import get_logger

logger = get_logger(__name__)


async def _format_havf_data(response: ChatResponse) -> list[dict]:
    """Format HAVF verification results for persistence."""
    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "paragraph_id": r.paragraph_id,
            "sentence_key": r.sentence_key,
        }
        for r in response.havf_results
    ]


async def _prepare_chat_context(session_id: str, db: AsyncSession) -> tuple[list[str], list]:
    """Validate session and retrieve papers and history."""
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise NotFoundError("Papers", f"no completed papers in session {session_id}")

    paper_ids = [str(p.id) for p in papers]
    history = await get_recent_messages(db, session_id, max_turns=4)
    return paper_ids, history


async def chat(
    session_id: str,
    query: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    llm: FallbackChain,
) -> ChatResponse:
    """Process a user query: retrieve → generate → verify → persist."""
    paper_ids, history = await _prepare_chat_context(session_id, db)
    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.USER,
        content=query,
    )
    response = await generate_response(
        query=query,
        paper_ids=paper_ids,
        history=history,
        faiss_store=faiss_store,
        llm=llm,
        db_session=db,
    )
    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=response.content,
        provider=response.provider.value,
        havf_results=await _format_havf_data(response),
        token_count=response.token_count,
        latency_ms=response.latency_ms,
    )
    return response


async def chat_stream(
    session_id: str,
    query: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    llm: FallbackChain,
):
    """
    Stream a chat response as SSE events.
    Returns an async generator of SSE-formatted strings.
    """
    paper_ids, history = await _prepare_chat_context(session_id, db)

    # Save user message
    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.USER,
        content=query,
    )

    return stream_chat_response(
        query=query,
        paper_ids=paper_ids,
        history=history,
        faiss_store=faiss_store,
        llm=llm,
        db_session=db,
    )
