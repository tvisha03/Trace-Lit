
from shared.constants import (
    CROSS_ENCODER_MODEL,
    HAVF_CROSS_ENCODER_THRESHOLD,
)
from shared.enums import ConfidenceLevel
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_cross_encoder = None

def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        with timer("Load cross-encoder"):
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder

def _update_result_confidence(best_score: float) -> ConfidenceLevel:
    if best_score >= HAVF_CROSS_ENCODER_THRESHOLD:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.MEDIUM

def _build_candidates(claim: str, result: dict, source_sentences: list[dict] | None, top_k: int) -> list[tuple[str, str]]:
    candidates = []
    if source_sentences:
        candidates = [
            (claim, s["text"])
            for s in source_sentences[:top_k * 3]
        ]
    elif result.get("source_sentence"):
        candidates = [(claim, result["source_sentence"])]
    return candidates

def _get_best_idx(scores) -> int:
    return int(scores.argmax()) if hasattr(scores, "argmax") else 0

def _process_scores(scores, best_idx: int) -> float:
    return float(scores[best_idx]) if hasattr(scores, "__getitem__") else float(scores)

def _update_source_reference(
    result: dict,
    source_sentences: list[dict] | None,
    best_idx: int,
) -> None:
    if not source_sentences or best_idx >= len(source_sentences):
        return

    best_source = source_sentences[best_idx]
    result["source_sentence"] = best_source["text"]
    result["paragraph_id"] = best_source["paragraph_id"]
    result["sentence_key"] = best_source.get("sentence_key")

def _process_result(
    result: dict,
    cross_encoder,
    source_sentences: list[dict] | None = None,
    top_k_sources: int = 3,
) -> dict:
    claim = result["claim"]
    candidates = _build_candidates(claim, result, source_sentences, top_k_sources)

    if not candidates:
        result["confidence"] = ConfidenceLevel.LOW
        return result

    scores = cross_encoder.predict(candidates)
    best_idx = _get_best_idx(scores)
    best_score = _process_scores(scores, best_idx)

    result["confidence"] = _update_result_confidence(best_score)
    result["best_score"] = best_score
    result["needs_reranking"] = False

    _update_source_reference(result, source_sentences, best_idx)
    return result

def rerank_claims(
    uncertain_results: list[dict],
    top_k_sources: int = 3,
    source_sentences: list[dict] | None = None,
) -> list[dict]:
    if not uncertain_results:
        return []

    cross_encoder = _get_cross_encoder()
    refined = [
        _process_result(result, cross_encoder, source_sentences, top_k_sources)
        for result in uncertain_results
    ]

    high_count = sum(1 for r in refined if r["confidence"] == ConfidenceLevel.HIGH)
    logger.info(f"Level 2 reranking: promoted {high_count}/{len(refined)} to HIGH")
    return refined
