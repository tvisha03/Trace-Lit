"""
HAVF — Hybrid Attribution Verification Framework.

Orchestrates the complete 2-stage verification pipeline:
  Level 1: Batch embedding similarity (handles ~89% of cases)
  Level 2: Cross-encoder reranking for uncertain claims

This is the CORE INNOVATION of Trace-Lit.
"""

from dataclasses import dataclass

from domain.verification.embedding_verifier import verify_claims_embedding
from domain.verification.reranker import rerank_claims
from shared.enums import ConfidenceLevel
from shared.utils.text_utils import split_into_sentences
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)


@dataclass
class VerificationResult:
    """Final HAVF result for a single generated claim."""
    claim: str
    confidence: ConfidenceLevel
    score: float
    source_sentence: str | None
    paragraph_id: str | None
    sentence_key: str | None


def build_source_sentences(chunks: list) -> list[dict]:
    """
    Flatten chunk sentence_maps into a flat list of source sentences
    for verification.

    Each entry: ``{"text", "paragraph_id", "sentence_key"}``
    """
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
) -> list[VerificationResult]:
    """
    Run the full HAVF pipeline on an LLM-generated response.

    Steps:
    1. Split generated text into individual claim sentences.
    2. Build source sentence pool from retrieved chunks.
    3. Level 1: batch embedding similarity.
    4. Level 2: cross-encoder reranking for uncertain claims.
    5. Merge and return final results.
    """
    with timer("HAVF verification"):
        claims = split_into_sentences(generated_text)
        if not claims:
            return []

        source_sentences = build_source_sentences(retrieved_chunks)
        if not source_sentences:
            # No source material — all claims are unverified
            return [
                VerificationResult(
                    claim=c,
                    confidence=ConfidenceLevel.LOW,
                    score=0.0,
                    source_sentence=None,
                    paragraph_id=None,
                    sentence_key=None,
                )
                for c in claims
            ]

        # --- Level 1: Embedding similarity ---
        level1_results = verify_claims_embedding(claims, source_sentences)

        # --- Level 2: Cross-encoder reranking for uncertain claims ---
        uncertain = [r for r in level1_results if r.get("needs_reranking")]
        resolved = [r for r in level1_results if not r.get("needs_reranking")]

        if uncertain:
            reranked = rerank_claims(uncertain, source_sentences=source_sentences)
            resolved.extend(reranked)

        # Convert to VerificationResult dataclass, preserving original claim order
        result_map = {r["claim"]: r for r in resolved}
        final: list[VerificationResult] = []

        for claim in claims:
            r = result_map.get(claim, {})
            final.append(VerificationResult(
                claim=claim,
                confidence=r.get("confidence", ConfidenceLevel.LOW),
                score=r.get("best_score", 0.0),
                source_sentence=r.get("source_sentence"),
                paragraph_id=r.get("paragraph_id"),
                sentence_key=r.get("sentence_key"),
            ))

        # Log summary statistics
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
