
import time
from dataclasses import dataclass

from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    COMPARISON_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.query_router import classify_query
from domain.retrieval.retriever import retrieve, RetrievedChunk
from domain.verification.havf import verify_response, VerificationResult
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.vector_store.faiss_store import FAISSStore
from app.config import get_settings
from shared.enums import LLMProvider, QueryType
from shared.logger import get_logger
from shared.utils.text_utils import estimate_tokens
from shared.utils.time_utils import timer

logger = get_logger(__name__)

@dataclass
class ChatResponse:
    content: str
    provider: LLMProvider
    havf_results: list[VerificationResult]
    retrieved_chunks: list[RetrievedChunk]
    token_count: int
    latency_ms: float

def _filter_chunks_by_keywords(
    chunks: list[RetrievedChunk],
    keywords: list[str] | None,
) -> list[RetrievedChunk]:
    if not keywords or not chunks:
        return chunks
    lower_kw = [kw.lower() for kw in keywords]
    return [c for c in chunks if any(kw in c.text.lower() for kw in lower_kw)]

def _build_user_prompt(
    query_type: QueryType,
    query: str,
    chunks: list[RetrievedChunk],
    history: list,
) -> str:
    context_block = build_context_block(chunks)
    history_block = build_history_block(history)

    if query_type == QueryType.COMPARISON:
        return CHAT_PROMPT_TEMPLATE.format(
            context=context_block,
            history=history_block,
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

async def _retrieve_and_filter_chunks(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    classification,
    keywords: list[str] | None,
) -> list[RetrievedChunk]:
    chunks = await retrieve(
        query=query,
        paper_ids=paper_ids,
        faiss_store=faiss_store,
        db_session=db_session,
        classification=classification,
    )
    return _filter_chunks_by_keywords(chunks, keywords)

async def _verify_response_with_settings(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> list[VerificationResult]:
    settings = get_settings()
    return await verify_response(
        response_text,
        chunks,
        high_threshold=settings.HAVF_HIGH_THRESHOLD,
        medium_threshold=settings.HAVF_MEDIUM_THRESHOLD,
        cross_encoder_threshold=settings.HAVF_CROSS_ENCODER_THRESHOLD,
    )

def _build_response(
    response_text: str,
    provider: LLMProvider,
    havf_results: list[VerificationResult],
    chunks: list[RetrievedChunk],
    latency_ms: float,
) -> ChatResponse:
    return ChatResponse(
        content=response_text,
        provider=provider,
        havf_results=havf_results,
        retrieved_chunks=chunks,
        token_count=estimate_tokens(response_text),
        latency_ms=latency_ms,
    )

async def generate_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
    keywords: list[str] | None = None,
) -> ChatResponse:
    start = time.perf_counter()

    classification = classify_query(
        query, history=history, paper_count=len(paper_ids),
    )

    if classification.query_type == QueryType.METADATA:
        return await _handle_metadata_query(
            query, paper_ids, history, llm, db_session, start,
        )

    chunks = await _retrieve_and_filter_chunks(
        query, paper_ids, faiss_store, db_session, classification, keywords,
    )

    user_prompt = _build_user_prompt(
        classification.query_type, query, chunks, history,
    )

    with timer("LLM generation"):
        settings = get_settings()
        response_text, provider, _ = await llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=settings.OLLAMA_MAX_TOKENS,
        )

    if not response_text or not response_text.strip():
        from shared.errors import EmptyResponseError
        raise EmptyResponseError(provider.value)

    havf_results = await _verify_response_with_settings(response_text, chunks)
    latency_ms = (time.perf_counter() - start) * 1000

    return _build_response(response_text, provider, havf_results, chunks, latency_ms)

async def _gather_paper_metadata(paper_ids: list[str], db_session) -> str:
    from infrastructure.db.crud.paper_crud import get_paper

    meta_lines: list[str] = []
    for pid in paper_ids:
        paper = await get_paper(db_session, pid)
        if paper is None:
            continue
        parts = [f"[Paper {pid[:8]}]"]
        if paper.title:
            parts.append(f"Title: {paper.title}")
        if paper.authors:
            parts.append(f"Authors: {paper.authors}")
        if paper.year:
            parts.append(f"Year: {paper.year}")
        if paper.abstract:
            parts.append(f"Abstract: {paper.abstract[:500]}")
        meta_lines.append("\n".join(parts))

    return "\n\n---\n\n".join(meta_lines) if meta_lines else "(No paper metadata available)"

async def _handle_metadata_query(
    query: str,
    paper_ids: list[str],
    history: list,
    llm: FallbackChain,
    db_session,
    start_time: float,
) -> ChatResponse:
    meta_context = await _gather_paper_metadata(paper_ids, db_session)

    user_prompt = CHAT_PROMPT_TEMPLATE.format(
        context=meta_context,
        history=build_history_block(history),
        question=query,
    )

    with timer("LLM generation (metadata)"):
        response_text, provider, _ = await llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    latency_ms = (time.perf_counter() - start_time) * 1000

    return ChatResponse(
        content=response_text,
        provider=provider,
        havf_results=[],
        retrieved_chunks=[],
        token_count=estimate_tokens(response_text),
        latency_ms=latency_ms,
    )

async def generate_comparison(
    paper_ids: list[str],
    paper_contexts: dict[str, str],
    llm: FallbackChain,
    question: str = "Compare these papers across all dimensions.",
    paper_titles: dict[str, str] | None = None,
) -> tuple[str, LLMProvider]:
    titles = paper_titles or {}
    paper_count = len(paper_ids)

    paper_listing_lines = []
    header_cols = []
    for i, pid in enumerate(paper_ids, start=1):
        name = titles.get(pid, f"Paper {pid[:8]}")
        paper_listing_lines.append(f"  {i}. {name}")
        header_cols.append(f"Paper {i}: {name}")
    paper_listing = "\n".join(paper_listing_lines)
    paper_listing_header = " | ".join(header_cols)
    paper_header_sep = " | ".join(["---"] * len(header_cols))

    formatted_contexts = "\n\n---\n\n".join(
        f"Paper {i}: {titles.get(pid, pid[:8])}\n{ctx}"
        for i, (pid, ctx) in enumerate(paper_contexts.items(), start=1)
    )

    user_prompt = COMPARISON_PROMPT_TEMPLATE.format(
        paper_count=paper_count,
        paper_listing=paper_listing,
        paper_listing_header=paper_listing_header,
        paper_header_sep=paper_header_sep,
        paper_contexts=formatted_contexts,
        question=question,
    )

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=4096,
    )
    return response_text, provider

async def generate_summary(
    context: str,
    llm: FallbackChain,
    question: str = "Summarize this paper.",
) -> tuple[str, LLMProvider]:
    user_prompt = SUMMARY_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
    )

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=4096,
    )
    return response_text, provider

