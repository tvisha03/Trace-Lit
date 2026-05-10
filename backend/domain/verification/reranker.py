from app.config import get_settings
from shared.enums import ConfidenceLevel
from shared.logger import get_logger
from shared.utils.time_utils import timer
import torch
import math

logger = get_logger(__name__)

_cross_encoder = None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        try:
            model_name = get_settings().CROSS_ENCODER_MODEL
            with timer("Load cross-encoder"):
                from sentence_transformers import CrossEncoder

                if torch.cuda.is_available():
                    device = "cuda"
                elif (
                    hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                ):
                    device = "mps"
                else:
                    device = "cpu"
                _cross_encoder = CrossEncoder(model_name, device=device)
                logger.info(f"Cross-encoder loaded on: {device}")
        except Exception as exc:
            logger.error(f"Cross-encoder unavailable: {exc}")
            return None
    return _cross_encoder


def _build_candidate_pairs(
    uncertain_results: list[dict],
    top_k_sources: int,
    source_sentences: list[dict] | None,
) -> tuple[list[tuple[str, str]], list[tuple]]:
    """Build (claim, source_text) pairs for cross-encoder scoring."""
    all_candidates = []
    claim_map = []
    
    # Pre-build an index of source sentences by paragraph_id for fast lookup
    source_index = {s["paragraph_id"]: s for s in (source_sentences or []) if s.get("paragraph_id")}

    for result in uncertain_results:
        claim = result["claim"]
        current_sources = source_sentences or []
        
        # Determine if there's an explicit citation in this claim
        from domain.verification.havf import _extract_cited_para_id
        cited_pid = _extract_cited_para_id(claim)
        
        # Filter candidate pool for this claim
        candidates = current_sources[: top_k_sources * 3]
        
        # CRITICAL: Always include the explicitly cited paragraph if we have it,
        # even if its embedding score was too low to be in the top candidates.
        if cited_pid and cited_pid in source_index:
            cited_src = source_index[cited_pid]
            if cited_src not in candidates:
                candidates.append(cited_src)

        if not candidates and result.get("source_sentence"):
            candidates = [
                {
                    "text": result["source_sentence"],
                    "paragraph_id": result.get("paragraph_id"),
                }
            ]

        for src in candidates:
            all_candidates.append((claim, src["text"]))
            claim_map.append((result, src))

    return all_candidates, claim_map


def _find_best_matches(all_scores: list[float], claim_map: list[tuple]) -> dict:
    """Find best source for each result from cross-encoder scores."""
    results_to_update = {}

    for i, score in enumerate(all_scores):
        res_obj, src_obj = claim_map[i]
        res_id = id(res_obj)
        if res_id not in results_to_update:
            results_to_update[res_id] = {"score": -1.0, "source": None}
        if score > results_to_update[res_id]["score"]:
            results_to_update[res_id]["score"] = score
            results_to_update[res_id]["source"] = src_obj

    return results_to_update


def _normalize_cross_encoder_score(raw_score: float) -> float:
    """Convert raw cross-encoder logit to 0-1 range via sigmoid.

    Cross-encoder models output raw logits (typically -5 to +10).
    Sigmoid maps these to (0, 1) so they're comparable to embedding
    cosine similarity scores used for confidence thresholds.
    """
    # Clamp to avoid overflow in exp()
    clamped = max(-500.0, min(500.0, raw_score))
    return float(1.0 / (1.0 + math.exp(-clamped)))


def _apply_rerank_results(
    result: dict,
    best_score: float,
    best_source: dict,
    cross_encoder_threshold: float,
    high_threshold: float,
) -> None:
    """Update result with reranking outcome."""
    if best_source:
        # Normalize raw cross-encoder logit to 0-1 range for comparison
        normalized_score = _normalize_cross_encoder_score(best_score)
        
        # Determine confidence level based on normalized score
        if normalized_score >= high_threshold:
            result["confidence"] = ConfidenceLevel.HIGH
        elif normalized_score >= cross_encoder_threshold:
            result["confidence"] = ConfidenceLevel.MEDIUM
        else:
            result["confidence"] = ConfidenceLevel.LOW
            
        result["best_score"] = normalized_score
        result["source_sentence"] = best_source["text"]
        result["paragraph_id"] = best_source.get("paragraph_id")
        result["paper_id"] = best_source.get("paper_id")
        result["sentence_key"] = best_source.get("sentence_key")
        result["page_number"] = best_source.get("page_number")
        result["cross_encoder_score"] = normalized_score
    else:
        result["confidence"] = ConfidenceLevel.LOW
    result["needs_reranking"] = False


def rerank_claims(
    uncertain_results: list[dict],
    top_k_sources: int = 3,
    source_sentences: list[dict] | None = None,
    *,
    cross_encoder_threshold: float | None = None,
    high_threshold: float | None = None,
) -> list[dict]:
    if not uncertain_results:
        return []

    cross_encoder = _get_cross_encoder()
    if cross_encoder is None:
        return uncertain_results

    settings = get_settings()
    if cross_encoder_threshold is None:
        cross_encoder_threshold = settings.HAVF_CROSS_ENCODER_THRESHOLD
    if high_threshold is None:
        high_threshold = settings.HAVF_HIGH_THRESHOLD

    all_candidates, claim_map = _build_candidate_pairs(
        uncertain_results, top_k_sources, source_sentences
    )
    if not all_candidates:
        return uncertain_results

    all_scores = cross_encoder.predict(all_candidates, batch_size=32)
    results_to_update = _find_best_matches(all_scores, claim_map)

    for result in uncertain_results:
        update_data = results_to_update.get(id(result)) or {
            "score": -1.0,
            "source": None,
        }
        best_score = float(update_data["score"])
        best_source = update_data["source"]
        _apply_rerank_results(
            result, best_score, best_source, cross_encoder_threshold, high_threshold
        )

    promoted_count = sum(
        1 for r in uncertain_results if r["confidence"] in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
    )
    logger.info(
        f"Level 2 reranking: resolved {promoted_count}/{len(uncertain_results)} claims"
    )

    return uncertain_results
