
from pathlib import Path
from dataclasses import dataclass, field

from shared.logger import get_logger
from shared.errors import PDFExtractionError
from shared.constants import FIGURE_IMAGE_FORMAT, FIGURE_IMAGE_DPI, FIGURE_MIN_SIZE_RATIO
from domain.extraction.table_extractor import (
    ExtractedTable,
    extract_tables_from_pages,
    extract_tables_from_pdf,
    merge_tables,
)
from domain.extraction.formula_extractor import (
    ExtractedFormula,
    extract_formulas_from_pages,
)

logger = get_logger(__name__)

@dataclass
class ExtractedFigure:
    image_path: str
    page_number: int
    bbox: tuple[float, float, float, float] | None = None
    caption: str = ""
    image_format: str = FIGURE_IMAGE_FORMAT

@dataclass
class ExtractedPage:
    page_number: int
    text: str
    tables: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    toc_items: list = field(default_factory=list)

@dataclass
class ExtractedDocument:
    markdown_text: str
    page_count: int
    filename: str
    pages: list[ExtractedPage] = field(default_factory=list)
    figures: list[ExtractedFigure] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    formulas: list[ExtractedFormula] = field(default_factory=list)


def _ensure_figure_dir(file_path: Path) -> Path:
    figure_dir = file_path.parent / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    return figure_dir


def _resolve_image_path(img_info, figure_dir: Path) -> Path | None:
    img_path = img_info if isinstance(img_info, str) else img_info.get("path", "")
    if not img_path:
        return None
    resolved = Path(img_path)
    if resolved.exists():
        return resolved
    alt = figure_dir / Path(img_path).name
    return alt if alt.exists() else None


def _extract_figures_from_pages(
    page_chunks: list[dict],
    figure_dir: Path,
) -> list[ExtractedFigure]:
    figures: list[ExtractedFigure] = []
    for page_data in page_chunks:
        page_num = page_data.get("metadata", {}).get("page", 0)
        for img_info in page_data.get("images", []):
            resolved = _resolve_image_path(img_info, figure_dir)
            if resolved is None:
                continue
            bbox = img_info.get("bbox") if isinstance(img_info, dict) else None
            figures.append(ExtractedFigure(
                image_path=str(resolved),
                page_number=page_num,
                bbox=tuple(bbox) if bbox else None,
            ))
    return figures


def _get_picture_boxes(page_data: dict) -> list[dict]:
    page_boxes = page_data.get("page_boxes", [])
    return [
        b for b in page_boxes
        if isinstance(b, dict) and b.get("class") == "picture"
    ]


def _render_box(page, rect, page_num: int, idx: int, figure_dir: Path) -> ExtractedFigure | None:
    import pymupdf as _pmu

    bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
    img_name = f"page{page_num}_fig{idx}.{FIGURE_IMAGE_FORMAT}"
    img_path = figure_dir / img_name

    if img_path.exists():
        return None

    pix = page.get_pixmap(clip=rect, dpi=FIGURE_IMAGE_DPI)
    pix.save(str(img_path))

    return ExtractedFigure(
        image_path=str(img_path),
        page_number=page_num,
        bbox=bbox,
    )


def _render_page_figures(
    doc, page_data: dict, figure_dir: Path
) -> list[ExtractedFigure]:
    import pymupdf

    page_num = page_data.get("metadata", {}).get("page", 0)
    picture_boxes = _get_picture_boxes(page_data)

    if not picture_boxes or page_num >= len(doc):
        return []

    page = doc[page_num]
    page_area = abs(page.rect.width * page.rect.height)
    rendered: list[ExtractedFigure] = []

    for idx, box in enumerate(picture_boxes):
        bbox = box.get("bbox")
        if not bbox or len(bbox) < 4:
            continue

        rect = pymupdf.Rect(bbox)
        if abs(rect.width * rect.height) / max(page_area, 1) < FIGURE_MIN_SIZE_RATIO:
            continue

        fig = _render_box(page, rect, page_num, idx, figure_dir)
        if fig:
            rendered.append(fig)

    return rendered


def _render_missing_figures(
    file_path: Path,
    page_chunks: list[dict],
    figure_dir: Path,
) -> list[ExtractedFigure]:
    import pymupdf

    rendered: list[ExtractedFigure] = []
    doc = pymupdf.open(str(file_path))
    try:
        for page_data in page_chunks:
            rendered.extend(_render_page_figures(doc, page_data, figure_dir))
    finally:
        doc.close()

    return rendered


def _build_pages(page_chunks: list[dict]) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    for page_data in page_chunks:
        meta = page_data.get("metadata", {})
        pages.append(ExtractedPage(
            page_number=meta.get("page", 0),
            text=page_data.get("text", ""),
            tables=page_data.get("tables", []),
            images=page_data.get("images", []),
            toc_items=page_data.get("toc_items", []),
        ))
    return pages


def _validate_pdf(file_path: Path) -> int:
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
    return page_count


def _run_layout_extraction(file_path: Path, figure_dir: Path) -> list[dict]:
    import pymupdf.layout  # pylint: disable=unused-import
    import pymupdf4llm

    return pymupdf4llm.to_markdown(
        str(file_path),
        page_chunks=True,
        write_images=True,
        image_path=str(figure_dir),
        image_format=FIGURE_IMAGE_FORMAT,
        image_size_limit=FIGURE_MIN_SIZE_RATIO,
        dpi=FIGURE_IMAGE_DPI,
        force_text=True,
    )


def _assemble_document(
    file_path: Path,
    page_chunks: list[dict],
    page_count: int,
    figure_dir: Path,
) -> ExtractedDocument:
    md_text = "\n\n".join(p.get("text", "") for p in page_chunks)

    if not md_text or len(md_text.strip()) < 100:
        raise PDFExtractionError(
            file_path.name,
            "extracted text is too short — the PDF may be scanned or image-only",
        )

    figures = _extract_figures_from_pages(page_chunks, figure_dir)
    rendered = _render_missing_figures(file_path, page_chunks, figure_dir)
    all_figures = figures + rendered
    pages = _build_pages(page_chunks)

    text_tables = extract_tables_from_pages(pages)
    pdf_tables = extract_tables_from_pdf(file_path)
    all_tables = merge_tables(text_tables, pdf_tables)

    all_formulas = extract_formulas_from_pages(pages)

    logger.info(
        f"Extracted {page_count} pages, {len(all_figures)} figures, "
        f"{len(all_tables)} tables, {len(all_formulas)} formulas "
        f"from {file_path.name} (layout mode)"
    )

    return ExtractedDocument(
        markdown_text=md_text,
        page_count=page_count,
        filename=file_path.name,
        pages=pages,
        figures=all_figures,
        tables=all_tables,
        formulas=all_formulas,
    )


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFExtractionError(file_path.name, "file not found")

    try:
        page_count = _validate_pdf(file_path)
        figure_dir = _ensure_figure_dir(file_path)
        page_chunks = _run_layout_extraction(file_path, figure_dir)
        return _assemble_document(file_path, page_chunks, page_count, figure_dir)

    except PDFExtractionError:
        raise
    except Exception as exc:
        logger.error(f"PDF extraction failed for {file_path.name}: {exc}")
        raise PDFExtractionError(file_path.name, str(exc))

