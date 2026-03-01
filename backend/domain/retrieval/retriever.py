"""TraceLit — Retriever.

Provides vector + DB fallback retrieval for the chat pipeline.
"""

import json
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from infrastructure.vector_store.faiss_store import get_vector_store


def retrieve_context_paragraphs(
    db: Session,
    paper_ids: List[str],
    query: str = "",
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve relevant paragraphs for a query using FAISS → DB fallback.

    Args:
        db: SQLAlchemy session (for fallback).
        paper_ids: Papers to search within.
        query: User query string for semantic ranking.
        top_k: Maximum results per call.

    Returns:
        List of paragraph dicts with metadata and sentences.
    """
    if not paper_ids:
        return []

    # --- Vector retrieval ---
    if query:
        try:
            results = get_vector_store().query(query_text=query, paper_ids=paper_ids, top_k=top_k)
            if results:
                logger.debug("Vector retrieval: {} paragraphs", len(results))
                return results
        except Exception as e:
            logger.warning("FAISS retrieval failed, falling back to DB: {}", e)

    # --- DB fallback (no semantic ranking) ---
    return _db_fallback(db, paper_ids, limit=50)


def _db_fallback(db: Session, paper_ids: List[str], limit: int = 50) -> List[Dict]:
    """Retrieve paragraphs directly from SQLite — no semantic ranking."""
    from infrastructure.db.models.paper import Paper
    from infrastructure.db.models.chunk import Paragraph

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.paper_id.in_(paper_ids))
        .limit(limit)
        .all()
    )

    paper_map = {}
    for pid in paper_ids:
        p = db.query(Paper).filter(Paper.id == pid).first()
        if p:
            paper_map[pid] = p

    context = []
    for para in paragraphs:
        paper = paper_map.get(para.paper_id)
        sentences = []
        if para.sentences:
            try:
                sentences = json.loads(para.sentences)
            except (json.JSONDecodeError, TypeError):
                sentences = []
        context.append({
            "paragraph_id": para.id,
            "text": para.text or "",
            "paper_id": para.paper_id,
            "paper_title": paper.title if paper else "Unknown",
            "section": "",
            "page": para.page or 0,
            "sentences": sentences,
        })

    return context
