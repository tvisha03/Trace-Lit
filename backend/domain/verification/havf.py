
import asyncio
from dataclasses import dataclass

from domain.verification.embedding_verifier import verify_claims_embedding
from domain.verification.reranker import rerank_claims
from shared.constants import (
    HAVF_HIGH_THRESHOLD,
    HAVF_MEDIUM_THRESHOLD,
    HAVF_CROSS_ENCODER_THRESHOLD,
)
from shared.enums import ConfidenceLevel, VerificationMethod
from shared.utils.text_utils import split_into_sentences
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

@dataclass
class VerificationResult:
    claim: str
    confidence: ConfidenceLevel
    score: float
    source_sentence: str | None
    paragraph_id: str | None
    sentence_key: str | None
    verification_method: "VerificationMethod | None" = None

def build_source_sentences(chunks: list) -> list[dict]:
    sources = []
    for chunk in chunks:
        s_map = chunk.sentence_map if hasattr(chunk, "sentence_map") else {}
        if isinstance(s_map, dict):
            for s_key, info in s_map.items():
                sources.append({
                    "text": info["text"],
                    "paragraph_id": chunk.paragraph_id if hasattr(chunk, "paragraph_id") else None,
                    "sentence_key": s_key,
                })
    return sources

async def verify_response(
    generated_text: str,
    retrieved_chunks: list,
    *,
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
    cross_encoder_threshold: float = HAVF_CROSS_ENCODER_THRESHOLD,
) -> list[VerificationResult]:
    with timer("HAVF verification"):
        claims = split_into_sentences(generated_text)
        source_sentences = build_source_sentences(retrieved_chunks)

        if not claims or not source_sentences:
            return _handle_missing_sources(claims)

        level1_results = await asyncio.to_thread(
            verify_claims_embedding, claims, source_sentences,
            high_threshold=high_threshold,
            medium_threshold=medium_threshold,
        )

        results = await _process_verification_results(
            level1_results, claims, source_sentences, cross_encoder_threshold
        )

        _log_verification_summary(results)
        return results


def _handle_missing_sources(claims: list[str]) -> list[VerificationResult]:
    """Return LOW confidence results when sources are unavailable."""
    if not claims:
        return []

    logger.warning(
        "HAVF: No source sentences found in retrieved chunks. "
        "All claims will be marked LOW confidence — citations "
        "may reference non-existent paragraphs."
    )
    return [
        VerificationResult(
            claim=c,
            confidence=ConfidenceLevel.LOW,
            score=0.0,
            source_sentence=None,
            paragraph_id=None,
            sentence_key=None,
            verification_method=VerificationMethod.SKIPPED,
        )
        for c in claims
    ]


async def _process_verification_results(
    level1_results: list,
    claims: list[str],
    source_sentences: list[dict],
    cross_encoder_threshold: float
) -> list[VerificationResult]:
    """Execute Level 2 reranking for uncertain claims and build final results."""
    uncertain = [r for r in level1_results if r.get("needs_reranking")]
    resolved = [r for r in level1_results if not r.get("needs_reranking")]

    if uncertain:
        reranked = await asyncio.to_thread(
            rerank_claims, uncertain,
            source_sentences=source_sentences,
            cross_encoder_threshold=cross_encoder_threshold,
        )
        resolved.extend(reranked)

    return _build_final_results(claims, resolved, uncertain)


def _build_final_results(
    claims: list[str],
    resolved: list,
    uncertain: list
) -> list[VerificationResult]:
    """Assemble VerificationResult objects with appropriate confidence and method."""
    result_map = {r["claim"]: r for r in resolved}
    uncertain_claims = {r["claim"] for r in uncertain}

    final = []
    for claim in claims:
        r = result_map.get(claim, {})
        method = _determine_verification_method(claim, r, uncertain_claims)
        final.append(VerificationResult(
            claim=claim,
            confidence=r.get("confidence", ConfidenceLevel.LOW),
            score=r.get("best_score", 0.0),
            source_sentence=r.get("source_sentence"),
            paragraph_id=r.get("paragraph_id"),
            sentence_key=r.get("sentence_key"),
            verification_method=method,
        ))
    return final


def _determine_verification_method(
    claim: str,
    result: dict,
    uncertain_claims: set
) -> VerificationMethod:
    """Determine which verification method produced the result."""
    if claim in uncertain_claims:
        return VerificationMethod.CROSS_ENCODER_RERANK
    elif result:
        return VerificationMethod.EMBEDDING_SIMILARITY
    else:
        return VerificationMethod.SKIPPED


def _log_verification_summary(results: list[VerificationResult]) -> None:
    """Log aggregate verification statistics."""
    counts = {level: 0 for level in ConfidenceLevel}
    for v in results:
        counts[v.confidence] += 1
    avg_score = sum(v.score for v in results) / len(results) if results else 0.0

    logger.info(
        f"HAVF complete: {len(results)} claims — "
        f"HIGH={counts[ConfidenceLevel.HIGH]}, "
        f"MEDIUM={counts[ConfidenceLevel.MEDIUM]}, "
        f"LOW={counts[ConfidenceLevel.LOW]}, "
        f"avg_score={avg_score:.3f}"
    )

