"""
PDF text extraction using PyMuPDF4LLM as the primary tool.
Outputs Markdown-formatted text with headings and paragraphs preserved.
"""

from pathlib import Path
from dataclasses import dataclass

from shared.logger import get_logger
from shared.errors import PDFExtractionError

logger = get_logger(__name__)


@dataclass
class ExtractedDocument:
    """Raw extraction result before section parsing."""
    markdown_text: str
    page_count: int
    filename: str


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    """
    Extract text from a PDF using PyMuPDF4LLM.

    Returns Markdown-formatted text with ``##`` headings and paragraph breaks.
    Raises PDFExtractionError on corrupt / unreadable files.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFExtractionError(file_path.name, "file not found")

    try:
        import pymupdf4llm
        import pymupdf

        doc = pymupdf.open(str(file_path))
        page_count = len(doc)
        doc.close()

        md_text: str = pymupdf4llm.to_markdown(str(file_path))

        if not md_text or len(md_text.strip()) < 100:
            raise PDFExtractionError(
                file_path.name,
                "extracted text is too short — the PDF may be scanned or image-only",
            )

        logger.info(f"Extracted {page_count} pages from {file_path.name}")
        return ExtractedDocument(
            markdown_text=md_text,
            page_count=page_count,
            filename=file_path.name,
        )

    except PDFExtractionError:
        raise
    except Exception as exc:
        logger.error(f"PDF extraction failed for {file_path.name}: {exc}")
        raise PDFExtractionError(file_path.name, str(exc))
