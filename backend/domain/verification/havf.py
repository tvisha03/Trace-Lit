import asyncio
import re
from dataclasses import dataclass
from domain.verification.embedding_verifier import verify_claims_embedding
from domain.verification.noise_filter import clean_source_text, is_noise_source
from domain.verification.reranker import rerank_claims
from app.config import get_settings
from shared.enums import ConfidenceLevel, VerificationMethod
from shared.utils.text_utils import split_into_sentences
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

# Standardized pattern: accepts 1-8 hex chars to match all valid citation formats
_CITATION_ID_RE = re.compile(r"\[((?:[a-f0-9]{1,8}_)?[PTFE]\d+)\]")
_MD_BOLD_RE = re.compile(r"\*{1,3}(.+?)\*{1,3}")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_LIST_RE = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
_MD_NUM_LIST_RE = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
_NON_TEXT_PREFIXES = frozenset({"F", "T", "E"})

_BRACKET_METADATA_RE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)+")
_CAPTION_EXTRACT_RE = re.compile(r"\[Caption:\s*(.+?)\]")
_TABLE_DESC_LINE_RE = re.compile(
    r"This (?:table|figure) is from the paper\s*'.+?'\.\s*"
    r"(?:It presents:.*?\.)?\s*"
    r"(?:The table contains.*?columns\.)?\s*",
    re.IGNORECASE,
)
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")
_MAX_DISPLAY_CHARS = 300


def _clean_table_source(stripped: str, caption: str | None) -> str:
    stripped = _TABLE_DESC_LINE_RE.sub("", stripped).strip()
    if caption:
        header_row = _find_first_table_header(stripped)
        return f"{caption}\n{header_row}" if header_row else caption
    lines = stripped.split("\n")
    return lines[0].strip() if lines else stripped


def _clean_figure_source(stripped: str, caption: str | None) -> str:
    if caption:
        return _MD_BOLD_RE.sub(r"\1", caption)
    lines = stripped.split("\n")
    return lines[0].strip() if lines else stripped


def _clean_formula_source(stripped: str) -> str:
    lines = stripped.split("\n")
    meaningful = [
        ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("##")
    ]
    return " ".join(meaningful[:2])


_CHUNK_SOURCE_CLEANERS = {
    "table": _clean_table_source,
    "figure": _clean_figure_source,
}


def _clean_source_for_display(
    source_text: str | None,
    chunk_type: str | None,
) -> str | None:
    if not source_text or chunk_type == "text" or chunk_type is None:
        return source_text

    caption_match = _CAPTION_EXTRACT_RE.search(source_text)
    caption = caption_match.group(1).strip() if caption_match else None
    stripped = _BRACKET_METADATA_RE.sub("", source_text).strip()

    cleaner = _CHUNK_SOURCE_CLEANERS.get(chunk_type)
    if cleaner:
        result = cleaner(stripped, caption)
    elif chunk_type == "formula":
        result = _clean_formula_source(stripped)
    else:
        result = stripped

    return _truncate_display(result, source_text)


def _truncate_display(result: str, fallback: str) -> str:
    if not result:
        return fallback
    if len(result) > _MAX_DISPLAY_CHARS:
        return result[:_MAX_DISPLAY_CHARS].rstrip() + "..."
    return result


def _find_first_table_header(text: str) -> str | None:
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("|") and not _TABLE_SEPARATOR_RE.match(line):
            return line
    return None


def _postprocess_display_sources(
    results: list["VerificationResult"],
) -> list["VerificationResult"]:
    return [
        VerificationResult(
            claim=r.claim,
            confidence=r.confidence,
            score=r.score,
            source_sentence=_clean_source_for_display(
                r.source_sentence,
                r.chunk_type,
            ),
            paragraph_id=r.paragraph_id,
            paper_id=r.paper_id,
            sentence_key=r.sentence_key,
            verification_method=r.verification_method,
            chunk_type=r.chunk_type,
            citation_ref=r.citation_ref,
            page_number=r.page_number,
        )
        for r in results
    ]


def _is_non_text_paragraph(paragraph_id: str | None) -> bool:
    if not paragraph_id:
        return False
    # Check for IDs like paperid_P1, paperid_F3, etc.
    if "_" in paragraph_id:
        suffix = paragraph_id.split("_")[-1]
        return suffix[:1] in _NON_TEXT_PREFIXES
    return paragraph_id[:1] in _NON_TEXT_PREFIXES


def _strip_markdown_for_claims(text: str) -> str:
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_LIST_RE.sub("", text)
    text = _MD_NUM_LIST_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_into_verifiable_claims(text: str) -> list[str]:
    cleaned = _strip_markdown_for_claims(text)
    paragraphs = re.split(r"\n\s*\n", cleaned)
    claims: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = split_into_sentences(para)
        claims.extend(sentences)
    return [c for c in claims if c.strip()]


def _extract_cited_para_id(claim: str) -> str | None:
    match = _CITATION_ID_RE.search(claim)
    return match.group(1) if match else None


def _build_para_source_index(source_sentences: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for src in source_sentences:
        pid = src.get("paragraph_id")
        if pid and pid not in index:
            index[pid] = src
    return index


def _apply_citation_correction(
    results: list["VerificationResult"],
    para_source_index: dict[str, dict],
    ce_threshold: float | None = None,
) -> list["VerificationResult"]:
    # Use settings value if not provided
    if ce_threshold is None:
        ce_threshold = get_settings().HAVF_CROSS_ENCODER_THRESHOLD
    corrected = []
    for result in results:
        cited_pid = _extract_cited_para_id(result.claim)
        if cited_pid and cited_pid in para_source_index:
            src = para_source_index[cited_pid]
            new_pid = src["paragraph_id"]
            chunk_type = _chunk_type_from_paragraph_id(new_pid)

            confidence = result.confidence
            score = result.score
            if chunk_type != "text" and _is_non_text_paragraph(new_pid):
                if confidence == ConfidenceLevel.LOW:
                    confidence = ConfidenceLevel.MEDIUM
                # Use the cross-encoder threshold as minimum for non-text chunks
                # to ensure consistency with Level 2 verification
                score = max(score, ce_threshold)

            result = VerificationResult(
                claim=result.claim,
                confidence=confidence,
                score=score,
                source_sentence=src["text"],
                paragraph_id=new_pid,
                paper_id=src["paper_id"],
                sentence_key=src["sentence_key"],
                verification_method=result.verification_method,
                chunk_type=chunk_type,
                citation_ref=new_pid.split("_")[-1] if new_pid else None,
                page_number=src.get("page_number"),
            )
        corrected.append(result)
    return corrected


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
    chunk_type: str | None = None
    citation_ref: str | None = None
    page_number: int | None = None


_PARAGRAPH_TYPE_MAP: dict[str, str] = {"F": "figure", "T": "table", "E": "formula"}


def _chunk_type_from_paragraph_id(paragraph_id: str | None) -> str:
    if not paragraph_id:
        return "text"
    # Logic to map 'P'->text, 'F'->figure, 'T'->table, 'E'->formula
    prefix = paragraph_id
    if "_" in paragraph_id:
        prefix = paragraph_id.split("_")[-1]

    indicator = prefix[:1]
    return _PARAGRAPH_TYPE_MAP.get(indicator, "text")


def _select_best_chunk_text(chunk) -> str:
    full_text = getattr(chunk, "text", "") or ""
    enriched_text = getattr(chunk, "enriched_text", "") or ""
    if len(enriched_text) > len(full_text):
        return enriched_text
    return full_text


def _should_add_source(cleaned: str, existing_texts: set[str]) -> bool:
    return bool(
        cleaned and cleaned not in existing_texts and not is_noise_source(cleaned)
    )


def _add_non_text_source(
    sources: list[dict], chunk, para_id: str | None, paper_id: str | None
) -> None:
    if not _is_non_text_paragraph(para_id):
        return
    best_text = _select_best_chunk_text(chunk)
    if len(best_text) <= 50:
        return
    cleaned = clean_source_text(best_text)
    existing_texts = {s["text"] for s in sources}
    if _should_add_source(cleaned, existing_texts):
        sources.append(
            {
                "text": cleaned,
                "paragraph_id": para_id,
                "paper_id": paper_id,
                "sentence_key": f"{para_id}_FULL" if para_id else None,
                "page_number": getattr(chunk, "page_number", None),
            }
        )


def _extract_chunk_sources(chunk) -> list[dict]:
    s_map = getattr(chunk, "sentence_map", {})
    if not isinstance(s_map, dict):
        s_map = {}
    raw_paper_id = getattr(chunk, "paper_id", None)
    paper_id = str(raw_paper_id) if raw_paper_id is not None else None
    para_id = getattr(chunk, "paragraph_id", None)
    sources = []
    for s_key, info in s_map.items():
        text = clean_source_text(info["text"])
        if not is_noise_source(text):
            sources.append(
                {
                    "text": text,
                    "paragraph_id": para_id,
                    "paper_id": paper_id,
                    "sentence_key": s_key,
                    "page_number": getattr(chunk, "page_number", None),
                }
            )
    _add_non_text_source(sources, chunk, para_id, paper_id)
    return sources


def build_source_sentences(chunks: list) -> list[dict]:
    sources = []
    for chunk in chunks:
        sources.extend(_extract_chunk_sources(chunk))
    return sources


def _initialize_havf_thresholds(
    high_threshold: float | None,
    medium_threshold: float | None,
    cross_encoder_threshold: float | None,
    short_sentence_words: int | None,
) -> tuple[float, float, float, int]:
    settings = get_settings()
    return (
        high_threshold or settings.HAVF_HIGH_THRESHOLD,
        medium_threshold or settings.HAVF_MEDIUM_THRESHOLD,
        cross_encoder_threshold or settings.HAVF_CROSS_ENCODER_THRESHOLD,
        short_sentence_words or settings.HAVF_SHORT_SENTENCE_WORDS,
    )


async def verify_response(
    generated_text: str,
    retrieved_chunks: list,
    *,
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
    cross_encoder_threshold: float | None = None,
    short_sentence_words: int | None = None,
) -> list[VerificationResult]:
    with timer("HAVF verification"):
        h_thresh, m_thresh, ce_thresh, short_words = _initialize_havf_thresholds(
            high_threshold,
            medium_threshold,
            cross_encoder_threshold,
            short_sentence_words,
        )
        claims = _split_into_verifiable_claims(generated_text)
        source_sentences = build_source_sentences(retrieved_chunks)
        if not claims or not source_sentences:
            return _handle_missing_sources(claims)
        short_claims, valid_claims = _filter_short_claims(claims, short_words)
        short_results = _create_skipped_results(short_claims)
        if not valid_claims:
            return short_results
        level1_results = await asyncio.to_thread(
            verify_claims_embedding,
            valid_claims,
            source_sentences,
            high_threshold=h_thresh,
            medium_threshold=m_thresh,
        )
        results = await _process_verification_results(
            level1_results, valid_claims, source_sentences, ce_thresh
        )
        all_results = short_results + results
        para_index = _build_para_source_index(source_sentences)
        all_results = _apply_citation_correction(all_results, para_index, ce_thresh)
        all_results = _postprocess_display_sources(all_results)
        _log_verification_summary(all_results)
        return all_results


def _filter_short_claims(
    claims: list[str], short_sentence_threshold: int
) -> tuple[list[str], list[str]]:
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
    cross_encoder_threshold: float,
) -> list[VerificationResult]:
    uncertain = [r for r in level1_results if r.get("needs_reranking")]
    resolved = [r for r in level1_results if not r.get("needs_reranking")]

    if uncertain:
        reranked = await asyncio.to_thread(
            rerank_claims,
            uncertain,
            source_sentences=source_sentences,
            cross_encoder_threshold=cross_encoder_threshold,
        )
        resolved.extend(reranked)

    return _build_final_results(claims, resolved, uncertain)


def _build_final_results(
    claims: list[str], resolved: list, uncertain: list
) -> list[VerificationResult]:
    result_map = {r["claim"]: r for r in resolved}
    uncertain_claims = {r["claim"] for r in uncertain}

    final = []
    for claim in claims:
        r = result_map.get(claim, {})
        method = _determine_verification_method(claim, r, uncertain_claims)
        p_id = r.get("paragraph_id")
        final.append(
            VerificationResult(
                claim=claim,
                confidence=r.get("confidence", ConfidenceLevel.LOW),
                score=min(1.0, max(0.0, float(r.get("best_score", 0.0)))),
                source_sentence=r.get("source_sentence"),
                paragraph_id=p_id,
                paper_id=r.get("paper_id"),
                sentence_key=r.get("sentence_key"),
                verification_method=method,
                chunk_type=_chunk_type_from_paragraph_id(p_id),
                citation_ref=p_id.split("_")[-1] if p_id else None,
                page_number=r.get("page_number"),
            )
        )
    return final


def _determine_verification_method(
    claim: str, result: dict, uncertain_claims: set
) -> VerificationMethod:
    if claim in uncertain_claims:
        return VerificationMethod.CROSS_ENCODER_RERANK
    elif result:
        return VerificationMethod.EMBEDDING_SIMILARITY
    else:
        return VerificationMethod.SKIPPED


def _log_verification_summary(results: list[VerificationResult]) -> None:
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
