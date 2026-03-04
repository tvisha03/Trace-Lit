
import asyncio
import re
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

# Inline image markdown pattern: ![alt](url) — from formula/figure extraction.
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

# Metadata patterns to exclude: table/figure/equation headers and structural labels
_TABLE_HEADER_RE = re.compile(r"^Table\s+\d+\s*:", re.IGNORECASE)
_FIGURE_HEADER_RE = re.compile(r"^Figure\s+\d+\s*:|^Fig\.\s+\d+\s*:", re.IGNORECASE)
_EQUATION_HEADER_RE = re.compile(r"^Eq(?:uation)?\s+\d+\s*:|^Formula\s+\d+\s*:", re.IGNORECASE)
_STRUCTURAL_LABEL_RE = re.compile(r"^(?:Stack|Goal|State|Input|Output)\s+\d*\s*:", re.IGNORECASE)

# Pattern for paragraph-id citation tags emitted by the LLM.
# Format: [<8-hex-chars>_<type><digits>] where type ∈ {P, T, F, E}.
# Example: [e35139f3_T100], [1d91788c_P354], [fa79fa43_E917]
_CITATION_ID_RE = re.compile(r"\[([a-f0-9]{8}_[PTFE]\d+)\]")


def _extract_cited_para_id(claim: str) -> str | None:
    """Return the first paragraph_id cited in *claim*, or None.

    The LLM appends citations as ``[paper_prefix_TypeIdx]``; the first match
    is the primary source the model claims to draw from.
    """
    match = _CITATION_ID_RE.search(claim)
    return match.group(1) if match else None


def _build_para_source_index(source_sentences: list[dict]) -> dict[str, dict]:
    """Map paragraph_id → first available source dict for citation lookup.

    For tables/figures/formulas there is typically only one sentence (caption
    or clean description), so the first entry found is the right one.
    """
    index: dict[str, dict] = {}
    for src in source_sentences:
        pid = src.get("paragraph_id")
        if pid and pid not in index:
            index[pid] = src
    return index


def _apply_citation_correction(
    results: list["VerificationResult"],
    para_source_index: dict[str, dict],
) -> list["VerificationResult"]:
    """Override source attribution when a claim cites a specific paragraph.

    The global embedding verifier finds the *best-matching* sentence across all
    sources, which can attribute a table-citing claim to a random text paragraph.
    This pass corrects the record: if the claim has a ``[T#]``, ``[F#]``, or
    ``[E#]`` tag *and* that chunk is present in the retrieved sources, we swap
    the source attribution to the actual cited chunk while keeping the original
    confidence score.
    """
    corrected = []
    for result in results:
        cited_pid = _extract_cited_para_id(result.claim)
        if cited_pid and cited_pid in para_source_index:
            src = para_source_index[cited_pid]
            new_pid = src["paragraph_id"]
            result = VerificationResult(
                claim=result.claim,
                confidence=result.confidence,
                score=result.score,
                source_sentence=src["text"],
                paragraph_id=new_pid,
                paper_id=src["paper_id"],
                sentence_key=src["sentence_key"],
                verification_method=result.verification_method,
                chunk_type=_chunk_type_from_paragraph_id(new_pid),
                citation_ref=new_pid.split("_")[-1] if new_pid else None,
            )
        corrected.append(result)
    return corrected


def _is_metadata_header(text: str) -> bool:
    """Check if text is a metadata header (table/figure/equation/structure label)."""
    return bool(
        _TABLE_HEADER_RE.match(text)
        or _FIGURE_HEADER_RE.match(text)
        or _EQUATION_HEADER_RE.match(text)
        or _STRUCTURAL_LABEL_RE.match(text)
    )


def _has_meaningful_content_after_images(text: str) -> bool:
    """Check if text has meaningful content after removing inline image markdown."""
    without_images = _IMG_MD_RE.sub("", text).strip()
    return len(without_images.split()) >= _MIN_SOURCE_SENTENCE_WORDS


def _is_noise_source(text: str) -> bool:
    """Return True for sentences that should not be used as verification sources.

    Filters out:
    - Very short entries (< 5 words)
    - Bibliography markers ("- [...")
    - Markdown table rows ("|...")
    - Metadata headers (table/figure/equation/structure labels)
    - Only image markdown with no real content
    """
    stripped = text.strip()

    # Too short or structural markers
    if (len(stripped.split()) < _MIN_SOURCE_SENTENCE_WORDS
        or stripped.startswith(("- [", "|"))
        or _is_metadata_header(stripped)):
        return True

    # Must have content after removing inline images
    return not _has_meaningful_content_after_images(stripped)
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


# Maps the leading character of a paragraph_id suffix to its content-type string.
# Keeps _chunk_type_from_paragraph_id branch-free for Codacy compliance.
_PARAGRAPH_TYPE_MAP: dict[str, str] = {"F": "figure", "T": "table", "E": "formula"}


def _chunk_type_from_paragraph_id(paragraph_id: str | None) -> str:
    """Derive content type string from a paragraph_id.

    paragraph_id format: ``{paper_id[:8]}_{TYPE}{idx}`` or bare ``{TYPE}{idx}``.
    TYPE is one of P (text), F (figure), T (table), E (formula/equation).
    Uses a dict lookup instead of chained if-checks to stay branch-free.
    """
    if not paragraph_id:
        return "text"
    # Take the last underscore-delimited segment; handles both prefixed and bare IDs.
    suffix = paragraph_id.split("_")[-1]
    return _PARAGRAPH_TYPE_MAP.get(suffix[:1], "text")

def _extract_chunk_sources(chunk) -> list[dict]:
    """Extract filtered source sentences from a single retrieved chunk.

    Uses getattr with defaults instead of ternary hasattr expressions to
    avoid unnecessary complexity branches that confuse static analysis.
    """
    s_map = getattr(chunk, "sentence_map", {})
    if not isinstance(s_map, dict):
        return []
    raw_paper_id = getattr(chunk, "paper_id", None)
    paper_id = str(raw_paper_id) if raw_paper_id is not None else None
    para_id = getattr(chunk, "paragraph_id", None)
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

        # Citation-aware correction: for claims that explicitly cite a paragraph
        # (e.g. [1d91788c_T100]), override the embedding-matched source with the
        # actual cited source so tables, figures, and formulas are always credited
        # to their own chunk rather than the nearest text paragraph.
        if source_sentences:
            para_index = _build_para_source_index(source_sentences)
            all_results = _apply_citation_correction(all_results, para_index)

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

