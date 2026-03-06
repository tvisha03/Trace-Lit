from app.config import get_settings
from shared.enums import ConfidenceLevel
from shared.logger import get_logger
from shared.utils.time_utils import timer
import torch

logger = get_logger(__name__)

_cross_encoder = None

def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        try:
            model_name = get_settings().CROSS_ENCODER_MODEL
            with timer("Load cross-encoder"):
                from sentence_transformers import CrossEncoder
                # Force CUDA to utilize your RTX 3060
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _cross_encoder = CrossEncoder(model_name, device=device)
                logger.info(f"Cross-encoder loaded on: {device}")
        except Exception as exc:
            logger.error(f"Cross-encoder unavailable: {exc}")
            return None
    return _cross_encoder

def rerank_claims(
    uncertain_results: list[dict],
    top_k_sources: int = 3,
    source_sentences: list[dict] | None = None,
    *,
    cross_encoder_threshold: float | None = None,
) -> list[dict]:
    if not uncertain_results:
        return []

    cross_encoder = _get_cross_encoder()
    if cross_encoder is None:
        return uncertain_results

    if cross_encoder_threshold is None:
        cross_encoder_threshold = get_settings().HAVF_CROSS_ENCODER_THRESHOLD

    all_candidates = []
    claim_map = []

    for result in uncertain_results:
        claim = result["claim"]
        current_sources = source_sentences if source_sentences else []
        if not current_sources and result.get("source_sentence"):
            current_sources = [{"text": result["source_sentence"], "paragraph_id": result.get("paragraph_id")}]

        candidates = current_sources[:top_k_sources * 3]
        for src in candidates:
            all_candidates.append((claim, src["text"]))
            claim_map.append((result, src))

    if not all_candidates:
        return uncertain_results

    all_scores = cross_encoder.predict(all_candidates, batch_size=32)
    results_to_update = {id(r): {"score": -1.0, "source": None} for r in uncertain_results}

    for i, score in enumerate(all_scores):
        res_obj, src_obj = claim_map[i]
        if score > results_to_update[id(res_obj)]["score"]:
            results_to_update[id(res_obj)]["score"] = score
            results_to_update[id(res_obj)]["source"] = src_obj

    for result in uncertain_results:
        update_data = results_to_update[id(result)]
        best_score = float(update_data["score"])
        best_source = update_data["source"]

        if best_source:
            result["confidence"] = ConfidenceLevel.MEDIUM if best_score >= cross_encoder_threshold else ConfidenceLevel.LOW
            result["best_score"] = best_score
            result["source_sentence"] = best_source["text"]
            result["paragraph_id"] = best_source.get("paragraph_id")
            result["paper_id"] = best_source.get("paper_id")
            result["sentence_key"] = best_source.get("sentence_key")

        result["needs_reranking"] = False

    medium_count = sum(1 for r in uncertain_results if r["confidence"] == ConfidenceLevel.MEDIUM)
    logger.info(f"Level 2 reranking: promoted {medium_count}/{len(uncertain_results)} to MEDIUM")

    return uncertain_results
