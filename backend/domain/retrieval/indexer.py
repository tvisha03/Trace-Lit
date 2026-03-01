"""TraceLit — Indexer.

Thin facade over VectorStore.add_paragraphs so services
don't import infrastructure directly.
"""

from typing import Any, Dict, List

from infrastructure.vector_store.faiss_store import get_vector_store


def index_paper_chunks(paper_id: str, chunks: List[Dict[str, Any]]) -> int:
    """Embed and store paragraph chunks for a paper.

    Args:
        paper_id: UUID of the paper.
        chunks: List of chunk dicts from SentenceAwareChunker.

    Returns:
        Number of paragraphs indexed.
    """
    return get_vector_store().add_paragraphs(paper_id, chunks)


def remove_paper_index(paper_id: str) -> int:
    """Delete all FAISS vectors for a paper. Returns deleted count."""
    return get_vector_store().delete_paper(paper_id)
