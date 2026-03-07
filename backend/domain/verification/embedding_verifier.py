
import numpy as np

from domain.retrieval.indexer import encode_texts
from shared.constants import HAVF_HIGH_THRESHOLD, HAVF_MEDIUM_THRESHOLD
from shared.enums import ConfidenceLevel
from shared.logger import get_logger

logger = get_logger(__name__)

def _determine_confidence(
    best_score: float,
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
) -> tuple[ConfidenceLevel, bool]:
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
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
) -> dict:
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
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
        "needs_reranking": needs_reranking,
    }

def _process_claims(
    claims: list[str],
    similarity_matrix: np.ndarray,
    source_sentences: list[dict],
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
) -> list[dict]:
    return [
        _build_result(
            i, claim, similarity_matrix[i], source_sentences,
            high_threshold, medium_threshold,
        )
        for i, claim in enumerate(claims)
    ]

def verify_claims_embedding(
    claims: list[str],
    source_sentences: list[dict],
    *,
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
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

    # Use cached embeddings when available (LAT-1: ~10-20x faster)
    source_vecs = _get_source_vectors(source_sentences)

    claim_vecs = encode_texts(claims)
    similarity_matrix = claim_vecs @ source_vecs.T

    results = _process_claims(
        claims, similarity_matrix, source_sentences,
        high_threshold, medium_threshold,
    )

    high_count = sum(1 for r in results if r["confidence"] == ConfidenceLevel.HIGH)
    cached_count = sum(1 for s in source_sentences if "embedding" in s)
    cache_status = f"cached={cached_count}/{len(source_sentences)}"
    logger.info(
        f"Level 1 verification: {high_count}/{len(results)} HIGH, "
        f"{sum(1 for r in results if r['needs_reranking'])} need reranking "
        f"({cache_status})"
    )
    return results


def _get_source_vectors(source_sentences: list[dict]) -> np.ndarray:
    """Build source embedding matrix, using cached vectors when available.

    Falls back to re-encoding for sentences without cached embeddings
    (e.g., non-text sources or chunks from before LAT-1 migration).
    """
    cached_indices: list[int] = []
    uncached_indices: list[int] = []

    for i, s in enumerate(source_sentences):
        if "embedding" in s:
            cached_indices.append(i)
        else:
            uncached_indices.append(i)

    n = len(source_sentences)

    # Fast path: all embeddings are cached
    if not uncached_indices:
        return np.array([s["embedding"] for s in source_sentences], dtype=np.float32)

    # Fast path: no cached embeddings, re-encode everything
    if not cached_indices:
        source_texts = [s["text"] for s in source_sentences]
        return encode_texts(source_texts)

    # Mixed: combine cached and freshly encoded
    from shared.constants import EMBEDDING_DIMENSIONS
    result = np.empty((n, EMBEDDING_DIMENSIONS), dtype=np.float32)

    for i in cached_indices:
        result[i] = source_sentences[i]["embedding"]

    uncached_texts = [source_sentences[i]["text"] for i in uncached_indices]
    uncached_vecs = encode_texts(uncached_texts)
    for j, i in enumerate(uncached_indices):
        result[i] = uncached_vecs[j]

    return result

