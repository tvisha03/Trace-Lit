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
from shared.utils.text_utils import extract_paragraph_ids, normalize_paragraph_ids

logger = get_logger(__name__)


async def validate_response_has_citations(
    response: str,
    context: list[dict],
    retrieved_paragraph_ids: list[str] | None = None,
) -> tuple[str, bool]:
    citation_pattern = r"\[((?:[a-f0-9]{1,8}_)?[PTFE]\d+)\]"
    citations_found = re.findall(citation_pattern, response)
    citations_stripped = False

    if not citations_found:
        if not context:
            return (
                "I couldn't find any relevant information in the provided papers to answer your question. Please try a different query or upload relevant papers.",
                True,
            )
        # LLM produced an answer but without traceable citations — surface the
        # answer rather than hiding it behind an opaque apology.  The disclaimer
        # lets the user know they should verify the content themselves.
        logger.warning(
            "validate_response_has_citations: LLM response contains no traceable "
            "paragraph citations. Returning the answer with an unverified disclaimer."
        )
        disclaimer = (
            "\n\n---\n"
            "_⚠️ Note: This response could not be automatically attributed to specific "
            "sections of the uploaded papers. Please verify the information independently._"
        )
        return (response.strip() + disclaimer, True)

    if retrieved_paragraph_ids:
        raw_cited = set(extract_paragraph_ids(response))
        valid_ids = set(retrieved_paragraph_ids)

        cited_ids, short_to_long = normalize_paragraph_ids(raw_cited, valid_ids)
        for short_id, long_id in short_to_long.items():
            response = response.replace(f"[{short_id}]", f"[{long_id}]")

        invalid_ids = cited_ids - valid_ids
        if invalid_ids:
            citations_stripped = True
            logger.warning(
                f"Stripping citations referencing non-existent paragraphs: {invalid_ids}. "
                f"Valid IDs: {valid_ids}"
            )
            for bad_id in invalid_ids:
                response = response.replace(f"[{bad_id}]", "")
            response = re.sub(r"  +", " ", response).strip()

    return response, citations_stripped


async def _format_havf_data(response: ChatResponse) -> list[dict]:
    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "source_sentence": r.source_sentence,
            "paragraph_id": r.paragraph_id,
            "paper_id": r.paper_id,
            "sentence_key": r.sentence_key,
            "verification_method": r.verification_method.value
            if r.verification_method
            else None,
            "chunk_type": r.chunk_type,
            "citation_ref": r.citation_ref,
            "page_number": r.page_number,
        }
        for r in response.havf_results
    ]


async def _validate_and_update_response_content(
    response: ChatResponse,
    paper_ids: list[str],
) -> None:
    retrieved_para_ids = [
        str(r.paragraph_id) for r in (response.retrieved_chunks or []) if r.paragraph_id
    ]
    validated_content, citations_stripped = await validate_response_has_citations(
        response.content,
        [{"paper_id": pid} for pid in paper_ids],
        retrieved_paragraph_ids=retrieved_para_ids or None,
    )
    response.content = validated_content
    if citations_stripped:
        # This fires when either (a) no citations were found and a disclaimer was
        # appended, or (b) some citations referenced non-existent paragraphs and
        # were stripped.  Both cases degrade attribution quality.
        logger.info(
            "Citation validation: response modified — citations absent or referencing unknown paragraphs"
        )


async def _process_and_save_response(
    response: ChatResponse,
    session_id: str,
    paper_ids: list[str],
    db: AsyncSession,
) -> None:
    is_metadata = not response.retrieved_chunks and not response.havf_results
    if not is_metadata:
        await _validate_and_update_response_content(response, paper_ids)

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


async def _prepare_chat_context(
    session_id: str, db: AsyncSession
) -> tuple[list[str], list]:
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        all_papers = await get_papers_by_session(db, session_id)
        if not all_papers:
            raise NotFoundError(
                "Papers",
                f"no papers uploaded in session {session_id}",
            )
        raise NotFoundError(
            "Papers",
            f"no completed papers in session {session_id} "
            f"({len(all_papers)} paper(s) still processing or failed)",
        )

    paper_ids = [str(p.id) for p in papers]
    history = await get_recent_messages(db, session_id, max_turns=4)
    return paper_ids, history


async def chat(
    session_id: str,
    query: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    keywords: list[str] | None = None,
) -> ChatResponse:
    paper_ids, history = await _prepare_chat_context(session_id, db)
    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.USER,
        content=query,
    )
    await db.commit()
    response = await generate_response(
        query=query,
        paper_ids=paper_ids,
        history=history,
        faiss_store=faiss_store,
        llm=llm,
        db_session=db,
        keywords=keywords,
    )
    await _process_and_save_response(response, session_id, paper_ids, db)
    return response


async def chat_stream(
    session_id: str,
    query: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    keywords: list[str] | None = None,
):
    try:
        paper_ids, history = await _prepare_chat_context(session_id, db)

        await create_message(
            db,
            session_id=session_id,
            role=MessageRole.USER,
            content=query,
        )
        await db.commit()

        return stream_chat_response(
            query=query,
            paper_ids=paper_ids,
            history=history,
            faiss_store=faiss_store,
            llm=llm,
            db_session=db,
            session_id=session_id,
            keywords=keywords,
        )
    except Exception as exc:
        logger.error(f"Error during chat stream setup: {exc}")
        raise
