
from __future__ import annotations

import json
from typing import AsyncGenerator, Tuple

from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import LLMProvider, QueryType
from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    COMPARISON_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.retriever import retrieve
from domain.retrieval.query_router import classify_query, QueryClassification
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.utils.streaming_utils import sse_event
from shared.logger import get_logger

logger = get_logger(__name__)

import re as _re
from shared.utils.text_utils import extract_paragraph_ids, normalize_paragraph_ids


def _validate_and_strip_citations(
    full_text: str,
    chunks: list,
    session_id: str,
) -> tuple[str, bool]:
    valid_pids = {c.paragraph_id for c in chunks}
    raw_cited = set(extract_paragraph_ids(full_text))

    cited_ids, short_to_long = normalize_paragraph_ids(raw_cited, valid_pids)
    for short_id, long_id in short_to_long.items():
        full_text = full_text.replace(f"[{short_id}]", f"[{long_id}]")

    invalid_ids = cited_ids - valid_pids
    if invalid_ids:
        logger.warning(
            f"Streaming response for session {session_id} cites non-existent "
            f"paragraphs {invalid_ids}. Stripping them before HAVF."
        )
        for bad_id in invalid_ids:
            full_text = full_text.replace(f"[{bad_id}]", "")
        full_text = _re.sub(r"  +", " ", full_text).strip()

    has_citations = bool(extract_paragraph_ids(full_text))
    if not has_citations:
        logger.warning(
            f"LLM response for session {session_id} contains no [P#]/[F#]/[T#]/[E#] citations. "
            "HAVF will have no citation targets — confidence scores may be unreliable."
        )
    return full_text, has_citations


async def _emit_havf_results(full_text: str, chunks: list):
    from domain.verification.havf import verify_response
    from app.config import get_settings
    settings = get_settings()
    havf_results = await verify_response(
        full_text,
        chunks,
        high_threshold=settings.HAVF_HIGH_THRESHOLD,
        medium_threshold=settings.HAVF_MEDIUM_THRESHOLD,
        cross_encoder_threshold=settings.HAVF_CROSS_ENCODER_THRESHOLD,
    )
    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "source_sentence": r.source_sentence,
            "paragraph_id": r.paragraph_id,
            "paper_id": r.paper_id,
            "sentence_key": r.sentence_key,
            "verification_method": r.verification_method.value if r.verification_method else None,
            # Content type and brief citation reference for non-text chunks (figures, tables, formulas)
            "chunk_type": r.chunk_type,
            "citation_ref": r.citation_ref,
        }
        for r in havf_results
    ]

def _strip_duplicate_prefix(accumulated: str, new_chunk: str) -> str:
    if not accumulated or not new_chunk:
        return new_chunk

    if new_chunk.startswith(accumulated):
        stripped = new_chunk[len(accumulated):]
        if stripped:
            logger.info(
                f"Duplicate token detection: stripped {len(accumulated)} chars "
                f"of duplicate prefix after provider switch"
            )
        return stripped

    max_overlap = min(len(accumulated), len(new_chunk))
    for overlap_len in range(max_overlap, 0, -1):
        if accumulated.endswith(new_chunk[:overlap_len]):
            stripped = new_chunk[overlap_len:]
            logger.info(
                f"Duplicate token detection: stripped {overlap_len} chars "
                f"of overlapping prefix after provider switch"
            )
            return stripped

    return new_chunk

async def _stream_tokens(llm: FallbackChain, user_prompt: str) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
    full_text = ""
    current_provider: LLMProvider | None = None

    async for token, provider_obj in llm.generate_streaming(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ):
        if current_provider is not None and provider_obj != current_provider:
            logger.info(
                f"Provider switch mid-stream: {current_provider.value} → {provider_obj.value}"
            )
            token = _strip_duplicate_prefix(full_text, token)
            if not token:
                current_provider = provider_obj
                continue

        current_provider = provider_obj
        full_text += token
        yield (token, provider_obj)

async def _classify_and_validate_query(
    query: str,
    paper_count: int,
    history: list,
) -> QueryClassification:
    try:
        return classify_query(query, history=history, paper_count=paper_count)
    except Exception as exc:
        logger.error(f"Query classification failed: {exc}")
        raise


async def _retrieve_and_filter_chunks(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    classification,
    keywords: list[str] | None = None,
) -> list:
    try:
        chunks = await retrieve(
            query=query,
            paper_ids=paper_ids,
            faiss_store=faiss_store,
            db_session=db_session,
            classification=classification,
        )
    except Exception as exc:
        logger.error(f"Retrieval failed during streaming: {exc}")
        raise

    if keywords and chunks:
        lower_kw = [kw.lower() for kw in keywords]
        chunks = [c for c in chunks if any(kw in c.text.lower() for kw in lower_kw)]
    return chunks


async def _persist_response(
    session_id: str,
    full_text: str,
    provider: str,
    havf_data: list,
    db_session,
) -> None:
    try:
        from infrastructure.db.crud.message_crud import create_message
        from shared.enums import MessageRole
        await create_message(
            db_session,
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=full_text,
            provider=provider,
            havf_results=havf_data,
        )
        await db_session.commit()
    except Exception as exc:
        logger.error(f"Failed to persist streaming assistant message for session {session_id}: {exc}")


def _build_streaming_prompt(
    classification,
    query: str,
    chunks: list,
    history: list,
) -> str:
    context_block = build_context_block(chunks)
    history_block = build_history_block(history)
    query_type = classification.query_type

    if query_type == QueryType.COMPARISON:
        return COMPARISON_PROMPT_TEMPLATE.format(
            paper_contexts=context_block,
            question=query,
        )
    if query_type == QueryType.SUMMARY:
        return SUMMARY_PROMPT_TEMPLATE.format(
            context=context_block,
            question=query,
        )
    return CHAT_PROMPT_TEMPLATE.format(
        context=context_block,
        history=history_block,
        question=query,
    )


async def stream_chat_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
    session_id: str,
    keywords: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    try:
        classification = await _classify_and_validate_query(query, len(paper_ids), history)
        yield sse_event("query_type", json.dumps({"type": classification.query_type.value}))

        chunks = await _retrieve_and_filter_chunks(
            query, paper_ids, faiss_store, db_session, classification, keywords
        )
        yield sse_event("sources", json.dumps([
            {"paragraph_id": c.paragraph_id, "paper_id": c.paper_id, "score": c.score}
            for c in chunks
        ]))

        user_prompt = _build_streaming_prompt(classification, query, chunks, history)

        full_text = ""
        provider = ""
        async for token, provider_obj in _stream_tokens(llm, user_prompt):
            full_text += token
            provider = provider_obj.value
            yield sse_event("token", {"token": token})

        resolved_provider = provider or "unknown"
        full_text, has_citations = _validate_and_strip_citations(full_text, chunks, session_id)

        if not has_citations:
            full_text = (
                "I was unable to provide a properly cited response based on "
                "the uploaded papers. Please try rephrasing your question or "
                "ensure the relevant papers have been uploaded."
            )
            yield sse_event("warning", json.dumps(
                {"detail": "Response replaced — no citations found. Confidence scores may be unreliable."}
            ))

        havf_data = await _emit_havf_results(full_text, chunks)
        yield sse_event("havf", json.dumps(havf_data))
        yield sse_event("done", json.dumps({"provider": resolved_provider, "full_text": full_text}))

        await _persist_response(session_id, full_text, resolved_provider, havf_data, db_session)

    except Exception as exc:
        logger.error(f"Streaming error: {exc}")
        yield sse_event("error", str(exc))
        yield sse_event("done", json.dumps({"provider": "", "full_text": "", "error": True}))

