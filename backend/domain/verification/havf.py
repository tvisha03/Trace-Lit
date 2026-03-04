
import asyncio
from dataclasses import dataclass

from domain.verification.embedding_verifier import verify_claims_embedding
from domain.verification.reranker import rerank_claims
from shared.constants import (
    HAVF_HIGH_THRESHOLD,
    HAVF_MEDIUM_THRESHOLD,
    HAVF_CROSS_ENCODER_THRESHOLD,
    HAVF_SHORT_SENTENCE_WORDS as _DEFAULT_SHORT_WORDS,  # Default fallback
)
from shared.enums import ConfidenceLevel, VerificationMethod
from shared.utils.text_utils import split_into_sentences
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

# Minimum word count for a source sentence to be used in verification.
# Sentences shorter than this are typically bibliography fragments, date stamps,
# or other noise (e.g. "B.", "- [400] S.", "Accessed: 2025-05-15.")
_MIN_SOURCE_SENTENCE_WORDS: int = 5


def _is_noise_source(text: str) -> bool:
    """Return True for sentences that should not be used as verification sources.

    Filters out:
    - Very short entries (< _MIN_SOURCE_SENTENCE_WORDS words)
    - Bibliography list markers that start with "- [" (e.g. "- [43] Art of Problem …")
    """
    stripped = text.strip()
    if len(stripped.split()) < _MIN_SOURCE_SENTENCE_WORDS:
        return True
    # Reference-list entries produced by markdown rendering of bibliography sections
    if stripped.startswith("- ["):
        return True
    return False


def _get_short_sentence_threshold() -> int:
    """Get the short sentence threshold from config, fallback to constants."""
    try:
        from app.config import get_settings
        return get_settings().HAVF_SHORT_SENTENCE_WORDS
    except Exception:
        return _DEFAULT_SHORT_WORDS

@dataclass
class VerificationResult:
    claim: str
    confidence: ConfidenceLevel
    score: float
    source_sentence: str | None
    paragraph_id: str | None
    paper_id: str | None
    sentence_key: str | None
    verification_method: "VerificationMethod | None" = None
    # Explicit content type derived from paragraph_id ("text", "figure", "table", "formula")
    chunk_type: str | None = None
    # Human-readable citation reference matching the paragraph_id suffix (e.g. "F3", "T1", "E2", "P5")
    citation_ref: str | None = None


def _chunk_type_from_paragraph_id(paragraph_id: str | None) -> str:
    """Derive content type string from a paragraph_id.

    paragraph_id format: ``{paper_id[:8]}_{TYPE}{idx}`` or bare ``{TYPE}{idx}``.
    TYPE is one of P (text), F (figure), T (table), E (formula/equation).
    """
    if not paragraph_id:
        return "text"
    # Take the last underscore-delimited segment; handles both prefixed and bare IDs.
    suffix = paragraph_id.split("_")[-1]
    if suffix.startswith("F"):
        return "figure"
    if suffix.startswith("T"):
        return "table"
    if suffix.startswith("E"):
        return "formula"
    return "text"

def _extract_chunk_sources(chunk) -> list[dict]:
    """Extract filtered source sentences from a single retrieved chunk."""
    s_map = chunk.sentence_map if hasattr(chunk, "sentence_map") else {}
    if not isinstance(s_map, dict):
        return []
    paper_id = str(chunk.paper_id) if hasattr(chunk, "paper_id") else None
    para_id = chunk.paragraph_id if hasattr(chunk, "paragraph_id") else None
    sources = []
    for s_key, info in s_map.items():
        text = info["text"]
        if not _is_noise_source(text):
            sources.append({
                "text": text,
                "paragraph_id": para_id,
                "paper_id": paper_id,
                "sentence_key": s_key,
            })
    return sources


def build_source_sentences(chunks: list) -> list[dict]:
    sources = []
    for chunk in chunks:
        sources.extend(_extract_chunk_sources(chunk))
    return sources

async def verify_response(
    generated_text: str,
    retrieved_chunks: list,
    *,
    high_threshold: float = HAVF_HIGH_THRESHOLD,
    medium_threshold: float = HAVF_MEDIUM_THRESHOLD,
    cross_encoder_threshold: float = HAVF_CROSS_ENCODER_THRESHOLD,
    short_sentence_words: int | None = None,  # MED-002: Allow override
) -> list[VerificationResult]:
    # MED-002: Use configurable threshold, default from settings
    if short_sentence_words is None:
        short_sentence_words = _get_short_sentence_threshold()

    with timer("HAVF verification"):
        claims = split_into_sentences(generated_text)
        source_sentences = build_source_sentences(retrieved_chunks)

        if not claims or not source_sentences:
            return _handle_missing_sources(claims)


        # FIXED MED-003: Filter out short sentences that shouldn't be verified
        # Short sentences (< 5 words) are often transitional phrases like "In contrast,"
        # or "Furthermore," which don't need verification
        short_claims, valid_claims = _filter_short_claims(claims, short_sentence_words)

        # Handle short claims by marking them as SKIPPED with LOW confidence
        short_results = _create_skipped_results(short_claims)

        # Only verify claims that have sufficient length
        if not valid_claims:
            # All claims were too short - return skipped results
            return short_results

        level1_results = await asyncio.to_thread(
            verify_claims_embedding, valid_claims, source_sentences,
            high_threshold=high_threshold,
            medium_threshold=medium_threshold,
        )

        results = await _process_verification_results(
            level1_results, valid_claims, source_sentences, cross_encoder_threshold
        )

        # Combine skipped results with verified results
        all_results = short_results + results

        _log_verification_summary(all_results)
        return all_results


def _filter_short_claims(claims: list[str], short_sentence_threshold: int) -> tuple[list[str], list[str]]:
    """Filter claims into short (< short_sentence_threshold) and valid claims.

    Returns tuple of (short_claims, valid_claims).
    """
    short_claims = []
    valid_claims = []

    for claim in claims:
        word_count = len(claim.split())
        if word_count < short_sentence_threshold:
            short_claims.append(claim)
        else:
            valid_claims.append(claim)

    if short_claims:
        logger.info(
            f"HAVF: Skipped {len(short_claims)} short sentences "
            f"(< {short_sentence_threshold} words) - marked as LOW confidence"
        )

    return short_claims, valid_claims


def _create_skipped_results(claims: list[str]) -> list[VerificationResult]:
    """Create verification results for skipped (too short) claims."""
    return [
        VerificationResult(
            claim=c,
            confidence=ConfidenceLevel.LOW,
            score=0.0,
            source_sentence=None,
            paragraph_id=None,
            paper_id=None,
            sentence_key=None,
            verification_method=VerificationMethod.SKIPPED,
        )
        for c in claims
    ]


def _handle_missing_sources(claims: list[str]) -> list[VerificationResult]:
    """Return LOW confidence results when sources are unavailable or sentences are too short.

    FIXED MED-003: Now handles both missing sources AND skipped short sentences.
    Short sentences (< HAVF_SHORT_SENTENCE_WORDS words) are marked as SKIPPED with LOW confidence.
    """
    if not claims:
        return []

    logger.warning(
        "HAVF: No source sentences found in retrieved chunks or sentences too short. "
        "All claims will be marked LOW confidence — citations "
        "may reference non-existent paragraphs or be transitional phrases."
    )
    return [
        VerificationResult(
            claim=c,
            confidence=ConfidenceLevel.LOW,
            score=0.0,
            source_sentence=None,
            paragraph_id=None,
            paper_id=None,
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
        p_id = r.get("paragraph_id")
        final.append(VerificationResult(
            claim=claim,
            confidence=r.get("confidence", ConfidenceLevel.LOW),
            score=r.get("best_score", 0.0),
            source_sentence=r.get("source_sentence"),
            paragraph_id=p_id,
            paper_id=r.get("paper_id"),
            sentence_key=r.get("sentence_key"),
            verification_method=method,
            chunk_type=_chunk_type_from_paragraph_id(p_id),
            # citation_ref is the type+index suffix, e.g. "F3", "T1", "E2", "P5"
            citation_ref=p_id.split("_")[-1] if p_id else None,
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

