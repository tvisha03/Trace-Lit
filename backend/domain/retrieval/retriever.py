"""
Retriever — fetches relevant chunks for a query using FAISS + budget-aware selection.

Per-paper top-k retrieval ensures balanced representation when querying
across multiple papers in the same session.
"""

from dataclasses import dataclass

from infrastructure.vector_store.faiss_store import FAISSStore
from domain.retrieval.indexer import encode_query
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from shared.constants import FAISS_TOP_K_PER_PAPER, MAX_CONTEXT_TOKENS
from shared.utils.text_utils import estimate_tokens
from shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    """A chunk returned from retrieval with its similarity score."""
    paragraph_id: str
    paper_id: str
    text: str
    enriched_text: str
    section_title: str | None
    score: float
    sentence_map: dict


async def retrieve(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    top_k: int = FAISS_TOP_K_PER_PAPER,
) -> list[RetrievedChunk]:
    """Retrieve top-k chunks per paper for the given query."""
    query_vector = encode_query(query)
    results = faiss_store.search(query_vector[0], paper_ids, top_k)
    if not results:
        return []

    composite_to_score = {f"{r['paper_id']}::{r['paragraph_id']}": r['score'] for r in results}
    para_by_paper: dict[str, list[str]] = {}
    for r in results:
        pid = r['paper_id']
        para_id = r['paragraph_id']
        para_by_paper.setdefault(pid, []).append(para_id)

    retrieved = []
    for paper_id, para_ids in para_by_paper.items():
        chunks = await get_chunks_by_paper(db_session, paper_id)
        for chunk in chunks:
            if chunk.paragraph_id in para_ids:
                cid = f"{paper_id}::{chunk.paragraph_id}"
                retrieved.append(RetrievedChunk(
                    paragraph_id=chunk.paragraph_id,
                    paper_id=str(chunk.paper_id),
                    text=chunk.text,
                    enriched_text=chunk.enriched_text,
                    section_title=chunk.section_title,
                    score=composite_to_score[cid],
                    sentence_map=chunk.sentence_map or {},
                ))
    retrieved.sort(key=lambda r: r.score, reverse=True)
    return _apply_token_budget(retrieved)


def _apply_token_budget(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep chunks until the rolling token total exceeds the context budget."""
    selected: list[RetrievedChunk] = []
    total_tokens = 0

    for chunk in chunks:
        tokens = estimate_tokens(chunk.text)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        selected.append(chunk)
        total_tokens += tokens

    return selected
