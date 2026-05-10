import hashlib

import numpy as np

from domain.retrieval.indexer import encode_texts
from app.config import get_settings
from shared.enums import ConfidenceLevel
from shared.logger import get_logger

logger = get_logger(__name__)

# LRU cache for source embeddings keyed by a hash of the source texts
_source_embedding_cache: dict[str, np.ndarray] = {}
_MAX_CACHE_ENTRIES = 50


def _source_cache_key(source_texts: list[str]) -> str:
    """Create a stable cache key from source texts."""
    content = "\n".join(source_texts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_source_embeddings(source_texts: list[str]) -> np.ndarray:
    """Return source embeddings, using cache if available."""
    key = _source_cache_key(source_texts)
    cached = _source_embedding_cache.get(key)
    if cached is not None:
        logger.debug(f"Source embedding cache HIT ({len(source_texts)} texts)")
        return cached

    vecs = encode_texts(source_texts)

    # Evict oldest entries if cache is full
    if len(_source_embedding_cache) >= _MAX_CACHE_ENTRIES:
        oldest_key = next(iter(_source_embedding_cache))
        del _source_embedding_cache[oldest_key]

    _source_embedding_cache[key] = vecs
    logger.debug(f"Source embedding cache MISS — encoded {len(source_texts)} texts")
    return vecs


def _determine_confidence(
    best_score: float,
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
) -> tuple[ConfidenceLevel, bool]:
    if high_threshold is None:
        high_threshold = get_settings().HAVF_HIGH_THRESHOLD
    if medium_threshold is None:
        medium_threshold = get_settings().HAVF_MEDIUM_THRESHOLD
    if best_score >= high_threshold:
        return ConfidenceLevel.HIGH, False
    elif best_score >= medium_threshold:
        return ConfidenceLevel.MEDIUM, True
    else:
        return ConfidenceLevel.LOW, False


def _build_result(
    i: int,
    claim: str,
    scores: np.ndarray,
    source_sentences: list[dict],
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
) -> dict:
    best_idx = int(np.argmax(scores))
    best_score = scores[best_idx].item()
    confidence, needs_reranking = _determine_confidence(
        best_score, high_threshold, medium_threshold
    )
    best_source = source_sentences[best_idx]
    return {
        "claim": claim,
        "confidence": confidence,
        "best_score": best_score,
        "source_sentence": best_source["text"],
        "paragraph_id": best_source["paragraph_id"],
        "paper_id": best_source.get("paper_id"),
        "sentence_key": best_source.get("sentence_key"),
        "page_number": best_source.get("page_number"),
        "full_context": best_source.get("full_context"),
        "needs_reranking": needs_reranking,
        "semantic_score": best_score,
    }


def _process_claims(
    claims: list[str],
    similarity_matrix: np.ndarray,
    source_sentences: list[dict],
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
) -> list[dict]:
    return [
        _build_result(
            i,
            claim,
            similarity_matrix[i],
            source_sentences,
            high_threshold,
            medium_threshold,
        )
        for i, claim in enumerate(claims)
    ]


def verify_claims_embedding(
    claims: list[str],
    source_sentences: list[dict],
    *,
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
) -> list[dict]:
    if not claims or not source_sentences:
        return [
            {
                "claim": c,
                "confidence": ConfidenceLevel.LOW,
                "best_score": 0.0,
                "source_sentence": None,
                "paragraph_id": None,
                "paper_id": None,
                "sentence_key": None,
                "needs_reranking": False,
            }
            for c in claims
        ]

    source_texts = [s["text"] for s in source_sentences]
    claim_vecs = encode_texts(claims)
    source_vecs = _get_source_embeddings(source_texts)
    similarity_matrix = claim_vecs @ source_vecs.T

    results = _process_claims(
        claims,
        similarity_matrix,
        source_sentences,
        high_threshold,
        medium_threshold,
    )

    high_count = sum(1 for r in results if r["confidence"] == ConfidenceLevel.HIGH)
    logger.info(
        f"Level 1 verification: {high_count}/{len(results)} HIGH, "
        f"{sum(1 for r in results if r['needs_reranking'])} need reranking"
    )
    return results
