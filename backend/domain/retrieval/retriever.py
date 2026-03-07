
from dataclasses import dataclass

from infrastructure.vector_store.faiss_store import FAISSStore
from domain.retrieval.indexer import encode_query
from domain.retrieval.query_router import QueryClassification, classify_query
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from shared.constants import (
    FAISS_TOP_K_PER_PAPER,
    MAX_CONTEXT_TOKENS,
    MAX_QUERY_TOKENS,
)
from shared.enums import QueryType
from shared.utils.text_utils import estimate_tokens, truncate_text
from shared.logger import get_logger

logger = get_logger(__name__)

_NON_TEXT_TYPES = frozenset({"figure", "table", "formula"})
_NON_TEXT_RESERVED_SLOTS = 3
_NON_TEXT_MIN_SCORE = 0.15

# Broad query types that need text paragraphs, not formulas/figures
_SKIP_NON_TEXT_BOOST_TYPES = frozenset({
    QueryType.COMPARISON,
    QueryType.SUMMARY,
})

# High-information sections that provide overview context for broad queries.
# Matched case-insensitively against section_title.
_OVERVIEW_SECTION_KEYWORDS = (
    "abstract", "introduction", "conclusion", "discussion",
    "related work", "overview", "background", "summary",
    "problem statement",
)
_OVERVIEW_SLOTS_PER_PAPER = 4

@dataclass
class RetrievedChunk:
    paragraph_id: str
    paper_id: str
    text: str
    enriched_text: str
    section_title: str | None
    score: float
    sentence_map: dict
    chunk_type: str | None = None
    sentence_embeddings: bytes | None = None

def _resolve_chunk_type(chunk) -> str | None:
    ct = getattr(chunk, "chunk_type", None)
    if ct is None:
        return None
    return ct.value if hasattr(ct, "value") else str(ct)

def _is_non_text_chunk(chunk) -> bool:
    return _resolve_chunk_type(chunk) in _NON_TEXT_TYPES

def _chunk_to_retrieved(chunk, score: float = _NON_TEXT_MIN_SCORE) -> RetrievedChunk:
    return RetrievedChunk(
        paragraph_id=chunk.paragraph_id,
        paper_id=str(chunk.paper_id),
        text=chunk.text,
        enriched_text=chunk.enriched_text,
        section_title=chunk.section_title,
        score=score,
        sentence_map=chunk.sentence_map or {},
        chunk_type=_resolve_chunk_type(chunk),
        sentence_embeddings=getattr(chunk, "sentence_embeddings", None),
    )

def _should_use_balanced_budget(classification: QueryClassification) -> bool:
    is_comparison_or_multi_hop = classification.query_type in (
        QueryType.COMPARISON,
        QueryType.MULTI_HOP,
    )
    return classification.balanced or is_comparison_or_multi_hop

def _process_faiss_results(
    results: list[dict],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    score_map = {f"{r['paper_id']}::{r['paragraph_id']}": r['score'] for r in results}
    para_by_paper: dict[str, list[str]] = {}
    for r in results:
        para_by_paper.setdefault(r['paper_id'], []).append(r['paragraph_id'])
    return score_map, para_by_paper

async def _build_chunks(
    results: list[dict],
    para_by_paper: dict[str, list[str]],
    score_map: dict[str, float],
    db_session,
) -> list[RetrievedChunk]:
    retrieved: list[RetrievedChunk] = []
    for paper_id, para_ids in para_by_paper.items():
        chunks = await get_chunks_by_paper(db_session, paper_id)
        para_set = set(para_ids)
        for chunk in chunks:
            if chunk.paragraph_id not in para_set:
                continue
            cid = f"{paper_id}::{chunk.paragraph_id}"
            if cid in score_map:
                score = score_map[cid]
            else:
                logger.warning(
                    f"Score map miss for {cid} — using 0.0. "
                    "Possible ID format mismatch between FAISS and DB."
                )
                score = 0.0
            retrieved.append(RetrievedChunk(
                paragraph_id=chunk.paragraph_id,
                paper_id=str(chunk.paper_id),
                text=chunk.text,
                enriched_text=chunk.enriched_text,
                section_title=chunk.section_title,
                score=score,
                sentence_map=chunk.sentence_map or {},
                chunk_type=_resolve_chunk_type(chunk),
                sentence_embeddings=getattr(chunk, "sentence_embeddings", None),
            ))
    return retrieved

async def _boost_non_text_chunks(
    retrieved: list[RetrievedChunk],
    para_by_paper: dict[str, list[str]],
    db_session,
    query_vector,
    faiss_store: FAISSStore,
    paper_ids: list[str],
) -> list[RetrievedChunk]:
    existing_pids = {(c.paper_id, c.paragraph_id) for c in retrieved}
    non_text_added: list[RetrievedChunk] = []
    for paper_id in paper_ids:
        paper_count = 0
        all_chunks = await get_chunks_by_paper(db_session, paper_id)
        for chunk in all_chunks:
            if not _is_non_text_chunk(chunk):
                continue
            if (str(chunk.paper_id), chunk.paragraph_id) in existing_pids:
                continue
            non_text_added.append(_chunk_to_retrieved(chunk))
            paper_count += 1
            if paper_count >= _NON_TEXT_RESERVED_SLOTS:
                break
    return retrieved + non_text_added


def _is_overview_section(section_title: str | None) -> bool:
    """Check if a chunk belongs to a high-information overview section."""
    if not section_title:
        return False
    lower = section_title.lower()
    return any(kw in lower for kw in _OVERVIEW_SECTION_KEYWORDS)


async def _boost_overview_sections(
    retrieved: list[RetrievedChunk],
    paper_ids: list[str],
    db_session,
) -> list[RetrievedChunk]:
    """Ensure overview sections (abstract, intro, conclusion) are
    represented in the context for broad query types."""
    existing_pids = {(c.paper_id, c.paragraph_id) for c in retrieved}
    overview_added: list[RetrievedChunk] = []

    for paper_id in paper_ids:
        paper_count = 0
        all_chunks = await get_chunks_by_paper(db_session, paper_id)
        for chunk in all_chunks:
            if _is_non_text_chunk(chunk):
                continue
            if not _is_overview_section(chunk.section_title):
                continue
            if (str(chunk.paper_id), chunk.paragraph_id) in existing_pids:
                continue
            overview_added.append(
                _chunk_to_retrieved(chunk, score=0.5)
            )
            paper_count += 1
            if paper_count >= _OVERVIEW_SLOTS_PER_PAPER:
                break

    if overview_added:
        logger.info(
            f"Boosted {len(overview_added)} overview-section chunks "
            f"({len(paper_ids)} papers)"
        )
    return retrieved + overview_added


async def retrieve(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    top_k: int = FAISS_TOP_K_PER_PAPER,
    classification: QueryClassification | None = None,
) -> list[RetrievedChunk]:
    if classification is None:
        classification = classify_query(query, paper_count=len(paper_ids))

    if classification.query_type == QueryType.METADATA:
        logger.info("Metadata query — skipping vector retrieval")
        return []

    if not faiss_store.is_ready():
        logger.warning("FAISS store not ready — returning empty results")
        return []

    effective_top_k = classification.retrieval_top_k or top_k
    query = truncate_text(query, MAX_QUERY_TOKENS)

    query_vector = encode_query(query)
    results = faiss_store.search(query_vector[0], paper_ids, effective_top_k)
    if not results:
        return []

    score_map, para_by_paper = _process_faiss_results(results)
    retrieved = await _build_chunks(results, para_by_paper, score_map, db_session)

    # Skip non-text boost for broad query types where formulas add noise
    if classification.query_type not in _SKIP_NON_TEXT_BOOST_TYPES:
        retrieved = await _boost_non_text_chunks(
            retrieved, para_by_paper, db_session,
            query_vector, faiss_store, paper_ids,
        )
    else:
        logger.info(
            f"Skipping non-text boost for {classification.query_type.value} query"
        )
        # Remove formula chunks entirely — they add noise for broad queries.
        # Tables are kept since they may contain useful comparative data.
        pre_count = len(retrieved)
        retrieved = [c for c in retrieved if c.chunk_type != "formula"]
        if len(retrieved) < pre_count:
            logger.info(
                f"Filtered {pre_count - len(retrieved)} formula chunks "
                f"for {classification.query_type.value} query"
            )

        # Inject overview-section chunks (abstract, intro, conclusion)
        # so the LLM has high-level context for broad queries.
        retrieved = await _boost_overview_sections(
            retrieved, paper_ids, db_session,
        )

    use_balanced = _should_use_balanced_budget(classification)

    return _apply_token_budget(retrieved, balanced=use_balanced)

def _apply_token_budget(
    chunks: list[RetrievedChunk],
    balanced: bool = True,
) -> list[RetrievedChunk]:
    if not balanced:
        return _greedy_budget(chunks)

    paper_best: dict[str, RetrievedChunk] = {}
    remaining: list[RetrievedChunk] = []

    for chunk in chunks:
        pid = chunk.paper_id
        if pid not in paper_best:
            paper_best[pid] = chunk
        else:
            remaining.append(chunk)

    selected: list[RetrievedChunk] = []
    total_tokens = 0

    for chunk in paper_best.values():
        tokens = estimate_tokens(chunk.text)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            continue
        selected.append(chunk)
        total_tokens += tokens

    remaining.sort(key=lambda c: c.score, reverse=True)
    for chunk in remaining:
        tokens = estimate_tokens(chunk.text)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            continue
        selected.append(chunk)
        total_tokens += tokens

    # Log chunk type distribution for debugging
    type_counts: dict[str, int] = {}
    for c in selected:
        ct = c.chunk_type or "text"
        type_counts[ct] = type_counts.get(ct, 0) + 1
    type_summary = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))

    logger.info(
        f"Token budget: {total_tokens}/{MAX_CONTEXT_TOKENS} tokens, "
        f"{len(selected)} chunks, {len(paper_best)} papers represented "
        f"[{type_summary}]"
    )
    return selected

def _greedy_budget(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    total_tokens = 0

    for chunk in chunks:
        tokens = estimate_tokens(chunk.text)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        selected.append(chunk)
        total_tokens += tokens

    return selected

