"""TraceLit — PDF Processor (PyMuPDF4LLM Wrapper).

Extracts structured content from academic PDFs:
  PDF → markdown (page-chunked) → section detection → metadata parsing

Uses PyMuPDF4LLM for extraction with page_chunks=True for section detection.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf4llm
from loguru import logger

from app.exceptions import ExtractionError


# ---------------------------------------------------------------------------
# Section heading detection patterns (ordered by specificity)
# ---------------------------------------------------------------------------

# Numbered sections: "1. Introduction", "2.1 Related Work", "A.1 Details"
# Must start with digit(s) or single uppercase letter + optional sub-numbers
_NUMBERED_HEADING_RE = re.compile(
    r"^([A-Z](?:\.\d+)*|\d+(?:\.\d+)*)\s*[.:\-)\s]\s*([A-Z][A-Za-z].+)",
)

# Markdown headings: "## Abstract", "### 3.1 Dataset"
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)")

# ALL-CAPS lines that look like headings: "ABSTRACT", "INTRODUCTION"
_ALLCAPS_HEADING_RE = re.compile(r"^([A-Z][A-Z\s]{3,})$")

# Common section titles (case-insensitive match)
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


def extract_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract structured content from a PDF using PyMuPDF4LLM.

    Args:
        pdf_path: Absolute or relative path to PDF file.

    Returns:
        {
            "metadata": {"title": ..., "authors": [...], "year": ..., "pages": ...},
            "sections": [
                {
                    "title": "Abstract",
                    "page_start": 1,
                    "order": 0,
                    "content": "Full text of the section..."
                },
                ...
            ],
            "raw_pages": [...]  # Per-page markdown (for debugging)
        }

    Raises:
        ExtractionError: If PyMuPDF4LLM fails or PDF is unreadable.
    """
    pdf_path = str(Path(pdf_path).resolve())
    logger.info("Starting PDF extraction: {}", pdf_path)

    try:
        page_chunks = pymupdf4llm.to_markdown(
            pdf_path,
            page_chunks=True,
            write_images=False,  # skip images for Phase 1
        )
    except Exception as exc:
        logger.error("PyMuPDF4LLM extraction failed for {}: {}", pdf_path, exc)
        raise ExtractionError(
            message=f"PDF extraction failed: {exc}",
            paper_id="",
        ) from exc

    if not page_chunks:
        raise ExtractionError(
            message="PDF produced no content",
            paper_id="",
        )

    # page_chunks is a list of dicts with keys: "metadata", "text", etc.
    raw_pages: List[str] = []
    for chunk in page_chunks:
        if isinstance(chunk, dict):
            raw_pages.append(chunk.get("text", ""))
        else:
            raw_pages.append(str(chunk))

    total_pages = len(raw_pages)
    logger.info("Extracted {} pages from PDF", total_pages)

    # --- Parse metadata from first page ---
    metadata = _parse_metadata(raw_pages[0] if raw_pages else "", total_pages)

    # --- Detect sections across all pages ---
    sections = _detect_sections(raw_pages)

    logger.info(
        "Extraction complete: {} sections, {} pages",
        len(sections),
        total_pages,
    )

    return {
        "metadata": metadata,
        "sections": sections,
        "raw_pages": raw_pages,
    }


# ---------------------------------------------------------------------------
# Metadata parsing
# ---------------------------------------------------------------------------

def _parse_metadata(first_page: str, total_pages: int) -> Dict[str, Any]:
    """Parse title, authors, and year from the first page of the paper.

    Uses heuristics — first non-empty line is the title,
    subsequent lines before the abstract are likely authors.
    """
    lines = [ln.strip() for ln in first_page.split("\n") if ln.strip()]

    title = "Untitled Paper"
    authors: List[str] = []
    year: Optional[int] = None

    if lines:
        # Title: first non-empty line, stripping markdown syntax + bold/italic
        title_line = lines[0]
        title = re.sub(r"^#+\s*", "", title_line).strip()
        title = re.sub(r"\*{1,2}|_{1,2}", "", title).strip()
        if not title:
            title = "Untitled Paper"

    # Year: find a 4-digit year (19xx or 20xx) anywhere on first page
    year_match = re.search(r"\b((?:19|20)\d{2})\b", first_page)
    if year_match:
        year = int(year_match.group(1))

    # Authors: lines between title and Abstract/Introduction
    # (simplistic heuristic — look for lines with commas or "and")
    abstract_idx = _find_abstract_line(lines)
    candidate_lines = lines[1:abstract_idx] if abstract_idx > 1 else lines[1:5]

    for ln in candidate_lines:
        # Skip lines that look like affiliations/emails
        if "@" in ln or "university" in ln.lower() or "department" in ln.lower():
            continue
        # Skip very short or very long lines
        if len(ln) < 3 or len(ln) > 300:
            continue
        # Lines with commas and short words are likely author lists
        if "," in ln or " and " in ln.lower():
            # Split on comma and "and"
            parts = re.split(r",\s*|\s+and\s+", ln)
            for part in parts:
                name = part.strip().rstrip("*†‡§∗1234567890")
                if 2 < len(name) < 60 and not name.startswith("http"):
                    authors.append(name)
            break  # Usually one author line is enough
        # If it's a standalone name-like line
        elif re.match(r"^[A-Z][a-z]+ [A-Z]", ln):
            authors.append(ln.strip().rstrip("*†‡§∗1234567890"))

    return {
        "title": title[:500],  # cap at 500 chars
        "authors": authors[:30],  # cap at 30 authors
        "year": year,
        "pages": total_pages,
    }


def _find_abstract_line(lines: List[str]) -> int:
    """Return index of the line containing 'Abstract'."""
    for i, ln in enumerate(lines):
        cleaned = re.sub(r"^#+\s*", "", ln).strip().lower()
        if cleaned in ("abstract", "abstract."):
            return i
    return min(len(lines), 8)  # default: assume first 8 lines are header


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def _detect_sections(pages: List[str]) -> List[Dict[str, Any]]:
    """Detect section boundaries across all pages.

    Returns a list of sections with title, page_start, order, and content.
    """
    # Merge all pages with page markers
    all_lines: List[Dict[str, Any]] = []
    for page_idx, page_text in enumerate(pages):
        for ln in page_text.split("\n"):
            all_lines.append({"text": ln, "page": page_idx + 1})

    # First pass: identify heading lines
    heading_indices: List[Dict[str, Any]] = []

    for i, line_info in enumerate(all_lines):
        text = line_info["text"].strip()
        if not text:
            continue

        heading = _classify_heading(text)
        if heading:
            heading_indices.append({
                "index": i,
                "title": heading,
                "page": line_info["page"],
            })

    # If no headings found, treat entire doc as single section
    if not heading_indices:
        full_text = "\n".join(li["text"] for li in all_lines)
        return [{
            "title": "Full Paper",
            "page_start": 1,
            "order": 0,
            "content": full_text.strip(),
        }]

    # Build sections from heading positions
    sections: List[Dict[str, Any]] = []

    # Content before first heading → "Header" section
    if heading_indices[0]["index"] > 0:
        pre_heading_text = "\n".join(
            all_lines[j]["text"] for j in range(heading_indices[0]["index"])
        )
        if pre_heading_text.strip():
            sections.append({
                "title": "Header",
                "page_start": 1,
                "order": 0,
                "content": pre_heading_text.strip(),
            })

    for idx, heading in enumerate(heading_indices):
        start = heading["index"] + 1  # line after heading
        end = (
            heading_indices[idx + 1]["index"]
            if idx + 1 < len(heading_indices)
            else len(all_lines)
        )

        section_text = "\n".join(
            all_lines[j]["text"] for j in range(start, end)
        )

        sections.append({
            "title": heading["title"],
            "page_start": heading["page"],
            "order": len(sections),
            "content": section_text.strip(),
        })

    # Filter out empty sections
    sections = [s for s in sections if s["content"]]

    logger.debug("Detected {} sections", len(sections))
    return sections


def _classify_heading(text: str) -> Optional[str]:
    """Classify a line as a section heading, returning the clean title or None.

    Conservative approach: only detect genuine section headings —
    markdown headings, numbered sections, ALL-CAPS known titles,
    or standalone known section names. Avoids false positives from
    sentences that happen to start with numbers or bold text.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 120:
        return None

    # Remove bold/italic markers for analysis
    clean_text = re.sub(r"\*{1,2}|_{1,2}", "", stripped).strip()

    # 1) Markdown heading: ## Title (must be a real heading marker)
    md_match = _MARKDOWN_HEADING_RE.match(stripped)
    if md_match:
        level = len(md_match.group(1))  # heading depth
        title = md_match.group(2).strip()
        title = re.sub(r"\*{1,2}|_{1,2}", "", title).strip()
        if level <= 3 and _is_plausible_heading(title):
            return _clean_heading(title)

    # 2) Numbered heading: must be short, standalone, start w/ number pattern
    #    e.g. "1 Introduction", "2.1 Related Work", "A.1 Details"
    #    Must NOT be a year like "2014." followed by a sentence
    num_match = _NUMBERED_HEADING_RE.match(clean_text)
    if num_match:
        number = num_match.group(1)
        title = num_match.group(2).strip()
        # Reject if number looks like a year (4 digits)
        if re.match(r"^\d{4}$", number):
            pass  # skip — likely a year reference
        elif _is_plausible_heading(title) and len(title.split()) <= 8:
            return _clean_heading(f"{number}. {title}")

    # 3) ALL-CAPS heading: ABSTRACT, INTRODUCTION
    caps_match = _ALLCAPS_HEADING_RE.match(clean_text)
    if caps_match:
        title = caps_match.group(1).strip().title()
        if title.lower().rstrip(".") in _KNOWN_SECTIONS:
            return title

    # 4) Known section name on its own line (case-insensitive, must be short)
    #    Must contain at least 2 words OR be exactly a known section name
    cleaned_lower = re.sub(r"^[#\d.\-)\s]+", "", clean_text).strip().lower().rstrip(".")
    if cleaned_lower in _KNOWN_SECTIONS and len(clean_text) < 40 and len(clean_text) > 4:
        return clean_text.strip().title()

    return None


def _is_plausible_heading(title: str) -> bool:
    """Check if a title is plausible (not a regular sentence)."""
    if not title:
        return False
    # Headings are typically short
    if len(title) > 100:
        return False
    # Headings typically don't end with period (unless abbreviated)
    if title.endswith(".") and title.lower().rstrip(".") not in _KNOWN_SECTIONS:
        word_count = len(title.split())
        if word_count > 6:
            return False
    return True


def _clean_heading(title: str) -> str:
    """Clean up heading text — remove trailing punctuation, extra whitespace."""
    title = re.sub(r"\s+", " ", title).strip()
    title = title.rstrip(":")
    return title
