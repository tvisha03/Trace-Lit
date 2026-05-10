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
import numpy as np
from sqlalchemy import select
import pymupdf
from infrastructure.db.database import async_session_factory
from infrastructure.db.models.paper import Paper
from domain.retrieval.indexer import encode_texts

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
    # If no caption, try to return a cleaner first line or just a label
    lines = stripped.split("\n")
    first = lines[0].strip() if lines else ""
    if "Figure" in first or "Fig." in first:
        return first
    return "Figure/Image Content"


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
    if not source_text:
        return source_text

    # Always strip system citation markers like [abc12345_P12] for display
    source_text = _CITATION_ID_RE.sub("", source_text).strip()

    if chunk_type == "text" or chunk_type is None:
        return _truncate_display(source_text, source_text)

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
            bbox=r.bbox,
            full_context=r.full_context,
            cross_encoder_score=r.cross_encoder_score,
            semantic_score=r.semantic_score,
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
            # Also handle the sentence-level key if needed, 
            # but primary index is by paragraph_id for citation matching
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
            
            # If the current result already matched the cited PID, keep it
            if result.paragraph_id == cited_pid:
                corrected.append(result)
                continue

            # If it matched something ELSE, we must re-evaluate against the cited PID
            # to ensure the 'Source' shown in UI actually matches the claim.
            logger.debug(f"Citation correction: overriding match {result.paragraph_id} with cited {cited_pid}")
            
            # Simple embedding check for the corrected source
            claim_vec = encode_texts([result.claim])
            src_vec = encode_texts([src["text"]])
            new_score = (claim_vec @ src_vec.T).item()
            
            settings = get_settings()
            new_conf = ConfidenceLevel.LOW
            if new_score >= settings.HAVF_HIGH_THRESHOLD:
                new_conf = ConfidenceLevel.HIGH
            elif new_score >= settings.HAVF_MEDIUM_THRESHOLD:
                new_conf = ConfidenceLevel.MEDIUM
            
            corrected.append(VerificationResult(
                claim=result.claim,
                confidence=new_conf,
                score=new_score,
                source_sentence=src["text"],
                paragraph_id=src["paragraph_id"],
                paper_id=src["paper_id"],
                sentence_key=src["sentence_key"],
                verification_method=VerificationMethod.EMBEDDING_SIMILARITY,
                chunk_type=_chunk_type_from_paragraph_id(src["paragraph_id"]),
                citation_ref=cited_pid.split("_")[-1] if cited_pid else None,
                page_number=src.get("page_number"),
                bbox=src.get("bbox"),
                full_context=src.get("full_context"),
                cross_encoder_score=result.cross_encoder_score,
                semantic_score=new_score,
            ))
        else:
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
    full_context: str | None = None
    bbox: dict | None = None
    cross_encoder_score: float | None = None
    semantic_score: float | None = None
    transformation_type: str | None = None
    transformation_confidence: float | None = None
    transformation_reason: str | None = None


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
    if len(best_text) <= 10:  # Reduced from 50 to 10 to catch short captions
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
                "full_context": getattr(chunk, "text", ""),
                "bbox": getattr(chunk, "bbox", None),
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
                    "full_context": getattr(chunk, "text", ""),
                    "bbox": getattr(chunk, "bbox", None),
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
            level1_results, valid_claims, source_sentences, ce_thresh, h_thresh
        )
        all_results = short_results + results
        para_index = _build_para_source_index(source_sentences)
        all_results = _apply_citation_correction(all_results, para_index, ce_thresh)
        all_results = _postprocess_display_sources(all_results)

        try:
            enhanced_results = []
            for r in all_results:
                if r.chunk_type == "table":
                    r = await _enhance_table_result(r)
                enhanced_results.append(r)
            all_results = enhanced_results
        except Exception as exc:
            logger.warning(f"Failed to enhance table bboxes: {exc}")

        _log_verification_summary(all_results)
        return all_results


async def _extract_table_caption_info(chunk_text: str) -> dict:
    from infrastructure.llm.fallback_chain import FallbackChain
    import json
    import re

    prompt = f"""You are extracting table identification information from a research paper chunk.

Given this retrieved chunk:
{chunk_text}

Extract the following in JSON format:
{{
  "table_number": <integer or null>,
  "table_caption": <full caption text as it appears, or null>,
  "caption_keywords": <3-5 distinctive words from caption for searching>,
  "has_numeric_data": <true/false>,
  "approximate_rows": <estimated number of data rows, or null>
}}

Rules:
- table_number: look for "Table 1", "Table 2", "Tab. 1" etc.
- table_caption: copy the caption EXACTLY as it appears in the chunk
- caption_keywords: pick unique words that would identify this specific table
- Only return what is explicitly in the chunk, never infer
- If no table is identified, return all fields as null"""

    try:
        llm = FallbackChain()
        res_text, provider, _ = await llm.generate(
            system_prompt="You are a helpful academic assistant that extracts info in JSON.",
            user_prompt=prompt,
        )
        match = re.search(r"\{.*\}", res_text, re.DOTALL)
        if match:
            res_text = match.group(0)
        return json.loads(res_text)
    except Exception as exc:
        logger.warning(f"Failed to extract table caption info: {exc}")
        return {
            "table_number": None,
            "table_caption": None,
            "caption_keywords": [],
            "has_numeric_data": False,
            "approximate_rows": None
        }


def _search_caption_on_page(doc, page_idx: int, caption_text: str, caption_keywords: list, table_number: int | None) -> tuple | None:
    if page_idx < 0 or page_idx >= len(doc):
        return None
    page = doc[page_idx]
    import re

    cleaned_caption = None
    if caption_text:
        cleaned_caption = re.sub(r"[\*\|]", "", caption_text)
        cleaned_caption = re.sub(r"\s+", " ", cleaned_caption).strip()

    if cleaned_caption:
        results = page.search_for(cleaned_caption)
        if results:
            return tuple(results[0])
        if len(cleaned_caption) > 12:
            results = page.search_for(cleaned_caption[:12])
            if results:
                return tuple(results[0])

    if table_number is not None:
        for prefix in [f"Table {table_number}", f"Tab. {table_number}", f"TABLE {table_number}"]:
            results = page.search_for(prefix)
            if results:
                return tuple(results[0])

    if caption_keywords:
        all_keyword_results = []
        for kw in caption_keywords:
            clean_kw = re.sub(r"[\*\|]", "", kw).strip()
            if len(clean_kw) >= 3:
                results = page.search_for(clean_kw)
                all_keyword_results.extend(results)
        
        if len(all_keyword_results) >= 2:
            min_x = min(r.x0 for r in all_keyword_results)
            min_y = min(r.y0 for r in all_keyword_results)
            max_x = max(r.x1 for r in all_keyword_results)
            max_y = max(r.y1 for r in all_keyword_results)
            return (min_x, min_y, max_x, max_y)

    return None


def _estimate_table_region(page, caption_bbox: tuple) -> tuple:
    x0, y0, x1, y1 = caption_bbox
    page_height = page.rect.height

    images_above = False
    images_below = False

    try:
        page_images = page.get_images(full=True)
        for img in page_images:
            try:
                xref = img[0]
                rects = page.get_image_rects(xref)
                for rect in rects:
                    if rect.y1 < y0:
                        images_above = True
                    if rect.y0 > y1:
                        images_below = True
            except Exception as e:
                logger.debug(f"Error reading image rects: {e}")
    except Exception as e:
        logger.debug(f"Error getting page images: {e}")

    if images_below:
        case = "above"
    elif images_above:
        case = "below"
    else:
        case = "below"

    if case == "above":
        est_bbox = (
            x0,
            y1 + 5,
            x1,
            min(y1 + 250, page_height - 30)
        )
    else:
        est_bbox = (
            x0,
            max(y0 - 250, 30),
            x1,
            y0 - 5
        )

    return est_bbox


def _compute_overlap(bbox1, bbox2) -> float:
    x0 = max(bbox1[0], bbox2[0])
    y0 = max(bbox1[1], bbox2[1])
    x1 = min(bbox1[2], bbox2[2])
    y1 = min(bbox1[3], bbox2[3])

    if x1 <= x0 or y1 <= y0:
        return 0.0

    intersection = (x1 - x0) * (y1 - y0)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    return intersection / area1 if area1 > 0 else 0.0


def _find_image_overlap(page, estimated_table_bbox: tuple) -> tuple | None:
    try:
        page_images = page.get_images(full=True)
        for img in page_images:
            xref = img[0]
            rects = page.get_image_rects(xref)
            for rect in rects:
                overlap = _compute_overlap(estimated_table_bbox, (rect.x0, rect.y0, rect.x1, rect.y1))
                if overlap > 0.3:
                    return (rect.x0, rect.y0, rect.x1, rect.y1)
    except Exception:
        pass
    return None


async def _verify_table_region(chunk_text: str, text_near_candidate: str) -> bool:
    from infrastructure.llm.fallback_chain import FallbackChain
    import json
    import re

    prompt = f"""You are verifying whether a found PDF region matches a retrieved table chunk.

RETRIEVED CHUNK (what RAG returned):
{chunk_text}

TEXT FOUND NEAR CANDIDATE LOCATION IN PDF:
{text_near_candidate}

Does the candidate location match the retrieved chunk?
Consider: table number, column headers, approximate data values

Return JSON:
{{
  "is_match": true | false,
  "confidence": "high" | "medium" | "low",
  "reason": "one sentence explanation"
}}"""

    try:
        llm = FallbackChain()
        res_text, provider, _ = await llm.generate(
            system_prompt="You are a helpful academic assistant that returns verification in JSON.",
            user_prompt=prompt,
        )
        match = re.search(r"\{.*\}", res_text, re.DOTALL)
        if match:
            res_text = match.group(0)
        data = json.loads(res_text)
        return data.get("is_match") is True and data.get("confidence") in ("high", "medium")
    except Exception as exc:
        logger.warning(f"Failed to verify table region via LLM: {exc}")
        return True


async def _enhance_table_result(r: VerificationResult) -> VerificationResult:
    if not r.paper_id:
        return r
    
    paper_path = None
    async with async_session_factory() as db:
        try:
            stmt = select(Paper).where(Paper.id == r.paper_id)
            res = await db.execute(stmt)
            paper = res.scalars().first()
            if paper:
                paper_path = paper.file_path
        except Exception as exc:
            logger.warning(f"Error fetching paper path for table bbox enhancement: {exc}")
    
    if not paper_path:
        return r

    chunk_text = r.full_context or r.source_sentence or ""
    if not chunk_text:
        return r

    info = await _extract_table_caption_info(chunk_text)
    table_num = info.get("table_number")
    caption_text = info.get("table_caption")
    keywords = info.get("caption_keywords") or []
    
    if caption_text:
        caption_text = re.sub(r"\s+", " ", caption_text).strip()

    try:
        doc = pymupdf.open(str(paper_path))
    except Exception as exc:
        logger.warning(f"Could not open PDF for table bbox: {exc}")
        return r

    try:
        orig_page = r.page_number if r.page_number is not None else 0
        page_idx = orig_page

        caption_bbox = None
        found_page_idx = page_idx

        search_pages = [page_idx]
        if page_idx - 1 >= 0:
            search_pages.append(page_idx - 1)
        if page_idx + 1 < len(doc):
            search_pages.append(page_idx + 1)
        for i in range(len(doc)):
            if i not in search_pages:
                search_pages.append(i)

        for p_idx in search_pages:
            if 0 <= p_idx < len(doc):
                caption_bbox = _search_caption_on_page(doc, p_idx, caption_text, keywords, table_num)
                if caption_bbox:
                    found_page_idx = p_idx
                    break

        page_height = doc[found_page_idx].rect.height
        page_width = doc[found_page_idx].rect.width

        if caption_bbox:
            estimated_table_bbox = _estimate_table_region(doc[found_page_idx], caption_bbox)
            actual_table_bbox = _find_image_overlap(doc[found_page_idx], estimated_table_bbox)
            
            text_rect = actual_table_bbox if actual_table_bbox else estimated_table_bbox
            try:
                text_near_candidate = doc[found_page_idx].get_text("text", clip=pymupdf.Rect(text_rect))
            except Exception:
                text_near_candidate = ""

            is_valid = await _verify_table_region(chunk_text, text_near_candidate)
            
            if is_valid:
                r.page_number = found_page_idx
                r.bbox = {
                    "source_type": "table",
                    "table_id": f"table_{found_page_idx}_{table_num or 0}",
                    "page": found_page_idx,
                    "caption_bbox": caption_bbox,
                    "table_bbox": actual_table_bbox or estimated_table_bbox,
                    "caption_text": caption_text or f"Table {table_num or 1}",
                }
        else:
            # Let's search for any image objects on the current page first
            first_image_rect = None
            try:
                page_images = doc[found_page_idx].get_images(full=True)
                for img in page_images:
                    xref = img[0]
                    rects = doc[found_page_idx].get_image_rects(xref)
                    if rects:
                        first_image_rect = (rects[0].x0, rects[0].y0, rects[0].x1, rects[0].y1)
                        break
            except Exception:
                pass

            r.bbox = {
                "source_type": "table",
                "table_id": f"table_{found_page_idx}_1",
                "page": found_page_idx,
                "table_bbox": first_image_rect or (50.0, page_height * 0.2, page_width - 50.0, page_height * 0.8),
                "caption_text": f"Table {table_num or 1}",
            }

    finally:
        doc.close()

    return r


def _filter_short_claims(
    claims: list[str], short_sentence_threshold: int
) -> tuple[list[str], list[str]]:
    short_claims = []
    valid_claims = []

    for claim in claims:
        word_count = len(claim.split())
        has_citation = bool(_CITATION_ID_RE.search(claim))
        
        if word_count < short_sentence_threshold and not has_citation:
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
    high_threshold: float,
) -> list[VerificationResult]:
    uncertain = [r for r in level1_results if r.get("needs_reranking")]
    resolved = [r for r in level1_results if not r.get("needs_reranking")]

    if uncertain:
        reranked = await asyncio.to_thread(
            rerank_claims,
            uncertain,
            source_sentences=source_sentences,
            cross_encoder_threshold=cross_encoder_threshold,
            high_threshold=high_threshold,
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
                bbox=r.get("bbox"),
                full_context=r.get("full_context"),
                cross_encoder_score=r.get("cross_encoder_score"),
                semantic_score=r.get("semantic_score", r.get("best_score")),
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
