
import numpy as np

from domain.retrieval.indexer import encode_texts
from shared.constants import HAVF_HIGH_THRESHOLD, HAVF_MEDIUM_THRESHOLD
from shared.enums import ConfidenceLevel
from shared.logger import get_logger

logger = get_logger(__name__)

def _determine_confidence(best_score: float) -> tuple[ConfidenceLevel, bool]:
    if best_score >= HAVF_HIGH_THRESHOLD:
        return ConfidenceLevel.HIGH, False
    elif best_score >= HAVF_MEDIUM_THRESHOLD:
        return ConfidenceLevel.MEDIUM, True
    else:
        return ConfidenceLevel.LOW, False

def _build_result(
    i: int,
    claim: str,
    scores: np.ndarray,
    source_sentences: list[dict],
) -> dict:
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    confidence, needs_reranking = _determine_confidence(best_score)
    best_source = source_sentences[best_idx]
    return {
        "claim": claim,
        "confidence": confidence,
        "best_score": best_score,
        "source_sentence": best_source["text"],
        "paragraph_id": best_source["paragraph_id"],
        "sentence_key": best_source.get("sentence_key"),
        "needs_reranking": needs_reranking,
    }

def _process_claims(
    claims: list[str],
    similarity_matrix: np.ndarray,
    source_sentences: list[dict],
) -> list[dict]:
    return [
        _build_result(i, claim, similarity_matrix[i], source_sentences)
        for i, claim in enumerate(claims)
    ]

def verify_claims_embedding(
    claims: list[str],
    source_sentences: list[dict],
) -> list[dict]:
    if not claims or not source_sentences:
        return [
            {
                "claim": c,
                "confidence": ConfidenceLevel.LOW,
                "best_score": 0.0,
                "source_sentence": None,
                "paragraph_id": None,
                "sentence_key": None,
                "needs_reranking": False,
            }
            for c in claims
        ]

    source_texts = [s["text"] for s in source_sentences]
    claim_vecs = encode_texts(claims)
    source_vecs = encode_texts(source_texts)
    similarity_matrix = claim_vecs @ source_vecs.T

    results = _process_claims(claims, similarity_matrix, source_sentences)

    high_count = sum(1 for r in results if r["confidence"] == ConfidenceLevel.HIGH)
    logger.info(
        f"Level 1 verification: {high_count}/{len(results)} HIGH, "
        f"{sum(1 for r in results if r['needs_reranking'])} need reranking"
    )
    return results
