import re
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


async def validate_response_has_citations(response: str, context: list[dict]) -> str:
    """Validate that response has proper citations or indicate not found.

    This is Layer 2 of HAVF hallucination prevention - ensuring the model
    actually cites sources for its claims.
    """
    # Check if response has any [P#] citations
    citation_pattern = r"\[P\d+\]"
    citations_found = re.findall(citation_pattern, response)

    if not citations_found:
        # No citations - check if context was empty
        if not context:
            return "I couldn't find any relevant information in the provided papers to answer your question. Please try a different query or upload relevant papers."
        # Context existed but model didn't cite - this is a hallucination risk
        return (
            "I don't see specific citations in my response. "
            "Let me reconsider...\n\n"
            "[Model should regenerate with proper citations]"
        )

    return response


async def _format_havf_data(response: ChatResponse) -> list[dict]:
    # All keys must match the VerificationItem schema so historical messages
    # deserialise correctly when later fetched via the messages endpoint.
    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "source_sentence": r.source_sentence,
            "paragraph_id": r.paragraph_id,
            "sentence_key": r.sentence_key,
        }
        for r in response.havf_results
    ]


async def _prepare_chat_context(
    session_id: str, db: AsyncSession
) -> tuple[list[str], list]:
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
    paper_ids, history = await _prepare_chat_context(session_id, db)
    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.USER,
        content=query,
    )
    # Commit the user message before invoking the LLM so it is persisted even
    # if generation fails — matching the explicit commit in the streaming path.
    await db.commit()
    response = await generate_response(
        query=query,
        paper_ids=paper_ids,
        history=history,
        faiss_store=faiss_store,
        llm=llm,
        db_session=db,
    )
    # Validate response has citations - Layer 2 of HAVF hallucination prevention
    validated_content = await validate_response_has_citations(
        response.content, [{"paper_id": pid} for pid in paper_ids]
    )
    response.content = validated_content
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
    """Stream chat response as SSE events.

    Saves the user message before streaming begins. The assistant message and HAVF
    results are persisted inside stream_chat_response once all tokens have been
    generated, while the db_session dependency is still open.
    """
    try:
        paper_ids, history = await _prepare_chat_context(session_id, db)

        await create_message(
            db,
            session_id=session_id,
            role=MessageRole.USER,
            content=query,
        )
        # Commit the user message before streaming so it is persisted even if
        # the stream fails partway through.
        await db.commit()

        return stream_chat_response(
            query=query,
            paper_ids=paper_ids,
            history=history,
            faiss_store=faiss_store,
            llm=llm,
            db_session=db,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error(f"Error during chat stream setup: {exc}")
        raise
