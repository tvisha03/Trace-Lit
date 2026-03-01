import json
from typing import AsyncGenerator

from infrastructure.llm.fallback_chain import FallbackChain
from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.retriever import retrieve
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.utils.streaming_utils import sse_event
from shared.logger import get_logger

logger = get_logger(__name__)


async def _emit_havf_results(full_text: str, chunks: list):
    """Build and return HAVF verification data."""
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


async def stream_chat_response(
    query: str, paper_ids: list[str], history: list, faiss_store: FAISSStore, llm: FallbackChain, db_session,
) -> AsyncGenerator[str, None]:
    """Stream a chat response as SSE events with retrieval, streaming, and verification."""
    provider = ""
    try:
        chunks = await retrieve(query=query, paper_ids=paper_ids, faiss_store=faiss_store, db_session=db_session)
        yield sse_event("sources", json.dumps([{"paragraph_id": c.paragraph_id, "paper_id": c.paper_id, "score": c.score} for c in chunks]))
        user_prompt = CHAT_PROMPT_TEMPLATE.format(
            context=build_context_block(chunks), history=build_history_block(history), question=query)
        full_text = ""
        async for token, provider_obj in llm.generate_streaming(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt):
            full_text += token
            provider = provider_obj.value
            yield sse_event("token", token)
        havf_data = await _emit_havf_results(full_text, chunks)
        yield sse_event("havf", json.dumps(havf_data))
        yield sse_event("done", json.dumps({"provider": provider, "full_text": full_text}))
    except Exception as exc:
        logger.error(f"Streaming error: {exc}")
        yield sse_event("error", str(exc))
