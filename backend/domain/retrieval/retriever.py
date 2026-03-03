
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

@dataclass
class RetrievedChunk:
    paragraph_id: str
    paper_id: str
    text: str
    enriched_text: str
    section_title: str | None
    score: float
    sentence_map: dict

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
            if chunk.paragraph_id in para_set:
                cid = f"{paper_id}::{chunk.paragraph_id}"
                score = score_map.get(cid, 0.0)
                if cid not in score_map:
                    logger.warning(
                        f"Score map miss for {cid} — using 0.0. "
                        "Possible ID format mismatch between FAISS and DB."
                    )
                retrieved.append(RetrievedChunk(
                    paragraph_id=chunk.paragraph_id,
                    paper_id=str(chunk.paper_id),
                    text=chunk.text,
                    enriched_text=chunk.enriched_text,
                    section_title=chunk.section_title,
                    score=score,
                    sentence_map=chunk.sentence_map or {},
                ))
    retrieved.sort(key=lambda r: r.score, reverse=True)
    return retrieved

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

    # EDGE-6: Guard against querying a FAISS index that hasn't been populated.
    if not faiss_store.is_ready():
        logger.warning("FAISS store not ready — returning empty results")
        return []

    effective_top_k = classification.retrieval_top_k or top_k

    # EDGE-2: Truncate extremely long queries before embedding to avoid
    # silent transformer truncation that could distort the vector.
    query = truncate_text(query, MAX_QUERY_TOKENS)

    query_vector = encode_query(query)
    results = faiss_store.search(query_vector[0], paper_ids, effective_top_k)
    if not results:
        return []

    score_map = {f"{r['paper_id']}::{r['paragraph_id']}": r['score'] for r in results}
    para_by_paper: dict[str, list[str]] = {}
    for r in results:
        para_by_paper.setdefault(r['paper_id'], []).append(r['paragraph_id'])

    retrieved = await _build_chunks(results, para_by_paper, score_map, db_session)

    use_balanced = classification.balanced or classification.query_type in (
        QueryType.COMPARISON, QueryType.MULTI_HOP,
    )
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

    logger.info(
        f"Token budget: {total_tokens}/{MAX_CONTEXT_TOKENS} tokens, "
        f"{len(selected)} chunks, {len(paper_best)} papers represented"
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
