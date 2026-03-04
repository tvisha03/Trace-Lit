"""TraceLit — PDF Processor (PyMuPDF4LLM Wrapper).

Extracts structured content from academic PDFs:
  PDF → markdown (page-chunked) → section detection → metadata parsing
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf4llm
import pymupdf.layout  # activates ONNX layout model — suppresses FutureWarning and enables improved page analysis
from loguru import logger

from domain.extraction.table_extractor import extract_tables, tables_to_markdown_sections
from shared.errors import ExtractionError


# ---------------------------------------------------------------------------
# Section heading patterns
# ---------------------------------------------------------------------------

_NUMBERED_HEADING_RE = re.compile(
    r"^([A-Z](?:\.\d+)*|\d+(?:\.\d+)*)\s*[.:\-)\s]\s*([A-Z][A-Za-z].+)",
)
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)")
_ALLCAPS_HEADING_RE = re.compile(r"^([A-Z][A-Z\s]{3,})$")

# ---------------------------------------------------------------------------
# Markdown artifact cleaner
# ---------------------------------------------------------------------------

def _clean_markdown_text(text: str) -> str:
    """Strip PyMuPDF4LLM inline markdown markers from extracted text.

    PyMuPDF4LLM sometimes wraps individual words in italic/bold markers
    (e.g. ``_The_ _detection_`` instead of ``The detection``).  This
    function removes those markers while preserving the underlying words.
    Order matters: bold-italic must be stripped before bold/italic.
    """
    # Bold-italic (*** or ___)
    text = re.sub(r'\*{3}(.+?)\*{3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{3}(.+?)_{3}', r'\1', text, flags=re.DOTALL)
    # Bold (** or __)
    text = re.sub(r'\*{2}(.+?)\*{2}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{2}(.+?)_{2}', r'\1', text, flags=re.DOTALL)
    # Italic (* or _)  — use non-greedy, single-line only to avoid cross-line collapse
    text = re.sub(r'\*([^\n*]+?)\*', r'\1', text)
    text = re.sub(r'_([^\n_]+?)_', r'\1', text)
    return text


_KNOWN_SECTIONS = {
    "abstract", "introduction", "related work", "background",
    "methodology", "method", "methods", "approach", "model",
    "experiments", "experimental setup", "evaluation",
    "results", "discussion", "conclusion", "conclusions",
    "acknowledgements", "acknowledgments", "references",
    "appendix", "supplementary material", "limitations",
    "future work", "dataset", "datasets", "implementation",
    "training", "analysis", "ablation", "ablation study",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract structured content from a PDF using PyMuPDF4LLM.

    Returns:
        {
            "metadata": {"title", "authors", "year", "pages"},
            "sections": [{"title", "page_start", "order", "content"}, ...],
            "raw_pages": [...]
        }
    """
    pdf_path = str(Path(pdf_path).resolve())
    logger.info("Starting PDF extraction: {}", pdf_path)

    try:
        page_chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True, write_images=False)
    except Exception as exc:
        raise ExtractionError(message=f"PDF extraction failed: {exc}", paper_id="") from exc

    if not page_chunks:
        raise ExtractionError(message="PDF produced no content", paper_id="")

    raw_pages: List[str] = []
    for chunk in page_chunks:
        raw_pages.append(chunk.get("text", "") if isinstance(chunk, dict) else str(chunk))

    total_pages = len(raw_pages)
    logger.info("Extracted {} pages from PDF", total_pages)

    metadata = _parse_metadata(raw_pages[0] if raw_pages else "", total_pages)
    sections = _detect_sections(raw_pages)

    # --- Table extraction ---------------------------------------------------
    try:
        tables = extract_tables(pdf_path, markdown_pages=raw_pages)
        if tables:
            table_sections = tables_to_markdown_sections(tables)
            sections.extend(table_sections)
            logger.info("Added {} table sections from PDF", len(table_sections))
    except Exception as exc:
        logger.warning("Table extraction failed (non-fatal): {}", exc)

    logger.info("Extraction complete: {} sections ({} tables), {} pages",
                len(sections), sum(1 for s in sections if s.get('is_table')), total_pages)
    return {"metadata": metadata, "sections": sections, "raw_pages": raw_pages}


async def extract_paper(pdf_path: str, mode: str = "auto") -> Dict[str, Any]:
    """Async wrapper for extract_pdf with mode selection.

    Runs synchronous PDF extraction in a thread to avoid blocking the event loop.
    All modes use PyMuPDF4LLM in Phase 1 (Docling added in Phase 2).
    """
    import asyncio

    logger.info("Extracting paper: mode={}, path={}", mode, pdf_path)
    result = await asyncio.to_thread(extract_pdf, pdf_path)
    logger.info(
        "Extraction complete: {} sections, {} pages (mode={})",
        len(result.get("sections", [])),
        result["metadata"].get("pages", 0),
        mode,
    )
    return result


# ---------------------------------------------------------------------------
# Metadata parsing
# ---------------------------------------------------------------------------

def _parse_metadata(first_page: str, total_pages: int) -> Dict[str, Any]:
    lines = [ln.strip() for ln in first_page.split("\n") if ln.strip()]
    title = "Untitled Paper"
    authors: List[str] = []
    year: Optional[int] = None

    if lines:
        title_line = lines[0]
        title = re.sub(r"^#+\s*", "", title_line).strip()
        title = re.sub(r"\*{1,2}|_{1,2}", "", title).strip() or "Untitled Paper"

    year_match = re.search(r"\b((?:19|20)\d{2})\b", first_page)
    if year_match:
        year = int(year_match.group(1))

    abstract_idx = _find_abstract_line(lines)
    candidate_lines = lines[1:abstract_idx] if abstract_idx > 1 else lines[1:5]

    for ln in candidate_lines:
        if "@" in ln or "university" in ln.lower() or "department" in ln.lower():
            continue
        if len(ln) < 3 or len(ln) > 300:
            continue
        if "," in ln or " and " in ln.lower():
            parts = re.split(r",\s*|\s+and\s+", ln)
            for part in parts:
                name = part.strip().rstrip("*†‡§∗1234567890")
                if 2 < len(name) < 60 and not name.startswith("http"):
                    authors.append(name)
            break
        elif re.match(r"^[A-Z][a-z]+ [A-Z]", ln):
            authors.append(ln.strip().rstrip("*†‡§∗1234567890"))

    return {"title": title[:500], "authors": authors[:30], "year": year, "pages": total_pages}


def _find_abstract_line(lines: List[str]) -> int:
    for i, ln in enumerate(lines):
        cleaned = re.sub(r"^#+\s*", "", ln).strip().lower()
        if cleaned in ("abstract", "abstract."):
            return i
    return min(len(lines), 8)


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def _detect_sections(pages: List[str]) -> List[Dict[str, Any]]:
    """Detect section boundaries across all pages."""
    all_lines: List[tuple] = []  # (page_num, line_text)
    for page_num, page_text in enumerate(pages, start=1):
        for line in page_text.split("\n"):
            all_lines.append((page_num, line.rstrip()))

    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None
    current_lines: List[str] = []

    def _flush_section():
        if current_section is not None:
            raw = "\n".join(current_lines).strip()
            current_section["content"] = _clean_markdown_text(raw)
            if current_section["content"]:
                sections.append(current_section)

    for page_num, line in all_lines:
        heading = _detect_heading(line)
        if heading:
            _flush_section()
            current_section = {
                "title": heading,
                "page_start": page_num,
                "order": len(sections),
                "content": "",
            }
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)
        else:
            # Content before first heading → "Preamble"
            if not sections:
                current_section = {"title": "Preamble", "page_start": page_num, "order": 0, "content": ""}
            current_lines.append(line)

    _flush_section()

    if not sections:
        full_text = _clean_markdown_text("\n".join(text for _, text in all_lines))
        sections = [{"title": "Full Text", "page_start": 1, "order": 0, "content": full_text}]

    return sections


def _detect_heading(line: str) -> Optional[str]:
    """Return a normalised heading string if the line is a section header."""
    stripped = line.strip()
    if not stripped or len(stripped) < 3 or len(stripped) > 120:
        return None

    # Markdown heading
    m = _MARKDOWN_HEADING_RE.match(stripped)
    if m:
        title = m.group(2).strip()
        return title if len(title) >= 3 else None

    # Numbered heading
    m = _NUMBERED_HEADING_RE.match(stripped)
    if m:
        return m.group(2).strip()

    # All-caps heading
    m = _ALLCAPS_HEADING_RE.match(stripped)
    if m:
        title = m.group(1).strip().title()
        if title.lower() in _KNOWN_SECTIONS:
            return title

    # Known section name (any case)
    if stripped.lower() in _KNOWN_SECTIONS:
        return stripped.title()

    return None
