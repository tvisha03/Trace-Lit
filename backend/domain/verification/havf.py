
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
    """Run the full HAVF pipeline (Level 1 embedding + Level 2 reranking).

    Thresholds default to the compile-time constants in ``shared.constants``
    but can be overridden at call time so operators may tune confidence
    cutoffs per-environment via ``Settings`` (HI-003).
    """
    with timer("HAVF verification"):
        claims = split_into_sentences(generated_text)
        if not claims:
            return []

        source_sentences = build_source_sentences(retrieved_chunks)
        if not source_sentences:
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

        # SentenceTransformer.encode() and CrossEncoder inference are blocking
        # CPU operations (100–500 ms each).  Running them in a thread pool via
        # asyncio.to_thread() keeps the event loop free during verification so
        # concurrent chat requests are not starved.
        level1_results = await asyncio.to_thread(
            verify_claims_embedding, claims, source_sentences,
            high_threshold=high_threshold,
            medium_threshold=medium_threshold,
        )

        uncertain = [r for r in level1_results if r.get("needs_reranking")]
        resolved = [r for r in level1_results if not r.get("needs_reranking")]

        if uncertain:
            reranked = await asyncio.to_thread(
                rerank_claims, uncertain,
                source_sentences=source_sentences,
                cross_encoder_threshold=cross_encoder_threshold,
            )
            resolved.extend(reranked)

        result_map = {r["claim"]: r for r in resolved}
        final: list[VerificationResult] = []

        # Build a set of claims that went through Level 2 reranking so we
        # can tag each result with the correct VerificationMethod.
        reranked_claims = {r["claim"] for r in uncertain}

        for claim in claims:
            r = result_map.get(claim, {})
            if claim in reranked_claims:
                method = VerificationMethod.CROSS_ENCODER_RERANK
            elif r:
                method = VerificationMethod.EMBEDDING_SIMILARITY
            else:
                method = VerificationMethod.SKIPPED
            final.append(VerificationResult(
                claim=claim,
                confidence=r.get("confidence", ConfidenceLevel.LOW),
                score=r.get("best_score", 0.0),
                source_sentence=r.get("source_sentence"),
                paragraph_id=r.get("paragraph_id"),
                sentence_key=r.get("sentence_key"),
                verification_method=method,
            ))

        counts = {level: 0 for level in ConfidenceLevel}
        for v in final:
            counts[v.confidence] += 1
        avg_score = sum(v.score for v in final) / len(final) if final else 0.0

        logger.info(
            f"HAVF complete: {len(final)} claims — "
            f"HIGH={counts[ConfidenceLevel.HIGH]}, "
            f"MEDIUM={counts[ConfidenceLevel.MEDIUM]}, "
            f"LOW={counts[ConfidenceLevel.LOW]}, "
            f"avg_score={avg_score:.3f}"
        )
        return final
