from app.config import get_settings
import re
from dataclasses import dataclass

from infrastructure.vector_store.faiss_store import FAISSStore
from domain.retrieval.indexer import encode_query
from domain.retrieval.query_router import QueryClassification, classify_query
from domain.retrieval.paper_detector import detect_target_papers
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.db.crud.paper_crud import get_paper
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

# Simple common stop words to filter from query for boosting
_STOP_WORDS = {
    "what", "is", "the", "exact", "how", "many", "where", "when", "which", "who", "whom",
    "this", "that", "these", "those", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", "the",
    "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for",
    "with", "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
    "over", "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"
}

def _get_query_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from the query for boosting."""
    # Split by non-alphanumeric and underscores
    words = re.findall(r'[a-zA-Z0-9_]+', query.lower())
    keywords = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    
    # Add common academic synonyms/variations
    extra = []
    for kw in keywords:
        if kw == "vocabulary": extra.append("vocab")
        if kw == "dimension": extra.extend(["dim", "dimensionality"])
        if kw == "transformer": extra.append("attention")
        if kw == "performance": extra.append("accuracy")
        if kw == "parameter": extra.append("param")
        if kw == "training": extra.append("train")
    
    return list(set(keywords + extra))

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
    page_number: int | None = None
    bbox: list[float] | None = None
    token_count: int = 0

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
        page_number=chunk.page_number if hasattr(chunk, "page_number") else None,
        bbox=chunk.bbox if hasattr(chunk, "bbox") else None,
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
    from infrastructure.db.crud.chunk_crud import get_chunks_by_paragraph_ids
    retrieved: list[RetrievedChunk] = []
    for paper_id, para_ids in para_by_paper.items():
        # Optimization: Only fetch the chunks we actually found in FAISS
        chunks = await get_chunks_by_paragraph_ids(db_session, paper_id, para_ids)
        for chunk in chunks:
            cid = f"{paper_id}::{chunk.paragraph_id}"
            score = score_map.get(cid, 0.0)
            retrieved.append(RetrievedChunk(
                paragraph_id=chunk.paragraph_id,
                paper_id=str(chunk.paper_id),
                text=chunk.text,
                enriched_text=chunk.enriched_text,
                section_title=chunk.section_title,
                score=score,
                sentence_map=chunk.sentence_map or {},
                chunk_type=_resolve_chunk_type(chunk),
                page_number=chunk.page_number if hasattr(chunk, "page_number") else None,
                bbox=chunk.bbox if hasattr(chunk, "bbox") else None,
                token_count=getattr(chunk, "token_count", 0) or estimate_tokens(chunk.text),
            ))
    return retrieved

async def _boost_non_text_chunks(
    retrieved: list[RetrievedChunk],
    para_by_paper: dict[str, list[str]],
    db_session,
    query_vector,
    faiss_store: FAISSStore,
    paper_ids: list[str],
    query: str = "",
) -> list[RetrievedChunk]:
    from infrastructure.db.crud.chunk_crud import get_non_text_chunks_by_paper
    existing_pids = {(c.paper_id, c.paragraph_id) for c in retrieved}
    non_text_added: list[RetrievedChunk] = []
    query_words = [w.lower() for w in query.split() if len(w) >= 3] if query else []
    
    for paper_id in paper_ids:
        paper_count = 0
        # Optimization: Only fetch non-text chunks (figures, tables, etc.)
        all_non_text = await get_non_text_chunks_by_paper(db_session, paper_id)
        
        scored_candidates = []
        for chunk in all_non_text:
            if (str(chunk.paper_id), chunk.paragraph_id) in existing_pids:
                continue
            
            match_count = sum(1 for w in query_words if w in (chunk.enriched_text or "").lower()) if query_words else 0
            score = _NON_TEXT_MIN_SCORE + (match_count * 0.1)
            scored_candidates.append((score, chunk))
        
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        for score, chunk in scored_candidates:
            non_text_added.append(_chunk_to_retrieved(chunk, score=score))
            paper_count += 1
            if paper_count >= _NON_TEXT_RESERVED_SLOTS:
                break
    return retrieved + non_text_added


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

    # Apply paper targeting boost
    try:
        papers_meta = []
        for pid in paper_ids:
            paper = await get_paper(db_session, pid)
            if paper:
                papers_meta.append({"id": str(paper.id), "title": paper.title or ""})
        
        paper_boosts = detect_target_papers(query, papers_meta)
        for r in results:
            boost = paper_boosts.get(r["paper_id"], 1.0)
            r["score"] = r["score"] * boost
    except Exception as e:
        logger.warning(f"Failed to apply paper boosts: {e}")

    score_map, para_by_paper = _process_faiss_results(results)
    retrieved = await _build_chunks(results, para_by_paper, score_map, db_session)
    
    # Apply keyword boosting on the retrieved chunks
    query_keywords = _get_query_keywords(query)
    if query_keywords:
        for chunk in retrieved:
            text_lower = chunk.text.lower()
            # Fuzzier matching: check if keyword is in text or text is in keyword
            # This handles dmodel vs d_model
            hits = 0
            for kw in query_keywords:
                clean_kw = kw.replace("_", "")
                clean_text = text_lower.replace("_", "")
                if kw in text_lower or clean_kw in clean_text:
                    hits += 1
            
            if hits > 0:
                boost = 1.0 + (hits * 0.15) # Increased boost for local models
                chunk.score *= boost
        
        # Re-sort after keyword boosting
        retrieved.sort(key=lambda x: x.score, reverse=True)

    # Context Scaling: If we are on a local model (Ollama), 
    # trim the context to 4k tokens so the model doesn't get "lost"
    settings = get_settings()
    is_local = settings.USE_LOCAL_LLM or not settings.has_llm_provider()
    local_cap = settings.OLLAMA_NUM_CTX - 500 # Leave room for prompt
    
    current_tokens = 0
    trimmed_retrieved = []
    for chunk in retrieved:
        chunk_tokens = chunk.token_count or estimate_tokens(chunk.text)
        if is_local and (current_tokens + chunk_tokens) > local_cap:
            break
        trimmed_retrieved.append(chunk)
        current_tokens += chunk_tokens
    
    retrieved = trimmed_retrieved

    retrieved = await _boost_non_text_chunks(
        retrieved, para_by_paper, db_session,
        query_vector, faiss_store, paper_ids, query=query,
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

