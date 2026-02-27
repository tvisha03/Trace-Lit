"""TraceLit — Hybrid PDF Extractor.

Supports three extraction modes:
  - auto  : Picks the best extractor based on PDF analysis (default)
  - fast  : Uses PyMuPDF4LLM only (fastest, good for most papers)
  - quality: Will use Docling in Phase 2 for table-heavy papers

For Phase 1, all modes route through PyMuPDF4LLM.
"""

from typing import Any, Dict, Literal

from loguru import logger

from app.extraction.pdf_processor import extract_pdf


ExtractionMode = Literal["auto", "fast", "quality"]


async def extract_paper(
    pdf_path: str,
    mode: ExtractionMode = "auto",
) -> Dict[str, Any]:
    """Extract structured content from a PDF.

    Args:
        pdf_path: Path to the PDF file.
        mode: Extraction mode — 'auto', 'fast', or 'quality'.

    Returns:
        Extraction result dict with metadata, sections, and raw_pages.
    """
    logger.info("Extracting paper: mode={}, path={}", mode, pdf_path)

    if mode == "quality":
        # Phase 2: Docling for table-heavy papers
        # For now, fall through to PyMuPDF4LLM
        logger.info("Quality mode requested — using PyMuPDF4LLM (Docling Phase 2)")

    elif mode == "auto":
        # Phase 2: auto-detect table density and pick extractor
        # For now, default to PyMuPDF4LLM
        logger.debug("Auto mode — defaulting to PyMuPDF4LLM")

    # All modes use PyMuPDF4LLM in Phase 1
    result = extract_pdf(pdf_path)

    section_count = len(result.get("sections", []))
    page_count = result["metadata"].get("pages", 0)
    logger.info(
        "Extraction complete: {} sections, {} pages (mode={})",
        section_count,
        page_count,
        mode,
    )

    return result
