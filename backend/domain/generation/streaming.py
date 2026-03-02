
from __future__ import annotations

import json
from typing import AsyncGenerator, Tuple

from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import LLMProvider
from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.retriever import retrieve
from domain.retrieval.query_router import classify_query
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.utils.streaming_utils import sse_event
from shared.logger import get_logger

logger = get_logger(__name__)

async def _emit_havf_results(full_text: str, chunks: list):
    from domain.verification.havf import verify_response
    havf_results = await verify_response(full_text, chunks)
    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "paragraph_id": r.paragraph_id,
            "sentence_key": r.sentence_key,
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

async def stream_chat_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
) -> AsyncGenerator[str, None]:
    provider = ""
    try:
        classification = classify_query(query, history=history, paper_count=len(paper_ids))
        yield sse_event("query_type", json.dumps({"type": classification.query_type.value}))

        chunks = await retrieve(
            query=query,
            paper_ids=paper_ids,
            faiss_store=faiss_store,
            db_session=db_session,
            classification=classification,
        )
        yield sse_event("sources", json.dumps([
            {"paragraph_id": c.paragraph_id, "paper_id": c.paper_id, "score": c.score}
            for c in chunks
        ]))

        user_prompt = CHAT_PROMPT_TEMPLATE.format(
            context=build_context_block(chunks),
            history=build_history_block(history),
            question=query,
        )

        full_text = ""
        async for token, provider_obj in _stream_tokens(llm, user_prompt):
            full_text += token
            provider = provider_obj.value
            yield sse_event("token", token)

        havf_data = await _emit_havf_results(full_text, chunks)
        yield sse_event("havf", json.dumps(havf_data))
        yield sse_event("done", json.dumps({"provider": provider, "full_text": full_text}))

    except Exception as exc:
        logger.error(f"Streaming error: {exc}")
        yield sse_event("error", str(exc))
