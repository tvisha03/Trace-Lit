
from pathlib import Path
from dataclasses import dataclass

from shared.logger import get_logger
from shared.errors import PDFExtractionError

logger = get_logger(__name__)

@dataclass
class ExtractedDocument:
    markdown_text: str
    page_count: int
    filename: str

def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFExtractionError(file_path.name, "file not found")

    try:
        import pymupdf4llm
        import pymupdf

        doc = pymupdf.open(str(file_path))

        if doc.needs_pass:
            doc.close()
            raise PDFExtractionError(
                file_path.name,
                "PDF is password-protected. Please provide an unlocked version of the file.",
            )

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

