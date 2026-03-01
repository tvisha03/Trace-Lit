"""
Chat Engine — orchestrates retrieval → generation → verification for each query.

Builds the full prompt, calls the LLM via the fallback chain, and runs HAVF
on the response before returning.
"""

from dataclasses import dataclass

from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    COMPARISON_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.retriever import retrieve, RetrievedChunk
from domain.verification.havf import verify_response, VerificationResult
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.enums import LLMProvider
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)


@dataclass
class ChatResponse:
    """Complete response with verification metadata."""
    content: str
    provider: LLMProvider
    havf_results: list[VerificationResult]
    retrieved_chunks: list[RetrievedChunk]
    token_count: int
    latency_ms: float


async def generate_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
) -> ChatResponse:
    """
    Full RAG pipeline: retrieve → build prompt → generate → verify.
    """
    import time
    start = time.perf_counter()

    # 1. Retrieve relevant chunks
    chunks = await retrieve(
        query=query,
        paper_ids=paper_ids,
        faiss_store=faiss_store,
        db_session=db_session,
    )

    # 2. Build prompt
    context_block = build_context_block(chunks)
    history_block = build_history_block(history)

    user_prompt = CHAT_PROMPT_TEMPLATE.format(
        context=context_block,
        history=history_block,
        question=query,
    )

    # 3. Generate response via LLM fallback chain
    with timer("LLM generation"):
        response_text, provider, _ = await llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    # 4. Verify with HAVF
    havf_results = await verify_response(response_text, chunks)

    latency_ms = (time.perf_counter() - start) * 1000
    from shared.utils.text_utils import estimate_tokens
    token_count = estimate_tokens(response_text)

    logger.info(f"Chat response: {token_count} tokens, {latency_ms:.0f}ms, provider={provider.value}")

    return ChatResponse(
        content=response_text,
        provider=provider,
        havf_results=havf_results,
        retrieved_chunks=chunks,
        token_count=token_count,
        latency_ms=latency_ms,
    )


async def generate_comparison(
    paper_ids: list[str],
    paper_contexts: dict[str, str],
    llm: FallbackChain,
) -> tuple[str, LLMProvider]:
    """Generate a structured comparison between papers."""
    formatted_contexts = "\n\n---\n\n".join(
        f"Paper: {pid}\n{ctx}" for pid, ctx in paper_contexts.items()
    )

    user_prompt = COMPARISON_PROMPT_TEMPLATE.format(paper_contexts=formatted_contexts)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    return response_text, provider


async def generate_summary(
    context: str,
    llm: FallbackChain,
) -> tuple[str, LLMProvider]:
    """Generate a structured summary for a single paper."""
    user_prompt = SUMMARY_PROMPT_TEMPLATE.format(context=context)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    return response_text, provider
