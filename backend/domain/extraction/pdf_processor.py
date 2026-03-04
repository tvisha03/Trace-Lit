from pathlib import Path
import re
from dataclasses import dataclass, field

try:
    import pymupdf.layout  # noqa: F401  # pylint: disable=unused-import
    _LAYOUT_MODE = True
except ImportError:
    _LAYOUT_MODE = False

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
    page_boxes: list[dict] = field(default_factory=list)

@dataclass
class ExtractedDocument:
    markdown_text: str
    page_count: int
    filename: str
    pages: list[ExtractedPage] = field(default_factory=list)
    figures: list[ExtractedFigure] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    formulas: list[ExtractedFormula] = field(default_factory=list)
    pdf_metadata: dict | None = None
    layout_mode: bool = False


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


_MD_IMAGE_RE = re.compile(r"!\[.*?\]\((.+?)\)")

_FIGURE_CAPTION_RE = re.compile(
    r"(?:Fig(?:ure|\.)?|FIGURE)\s+(\d+)[.:]?\s*(.*)",
    re.IGNORECASE,
)


def _find_figure_caption(page_text: str, image_pos: int) -> str:
    search_after = page_text[image_pos:image_pos + 400]
    search_before = page_text[max(0, image_pos - 400):image_pos]

    for region in (search_after, search_before):
        lines = region.strip().split("\n")
        candidates = lines[:6] if region is search_after else lines[-6:]
        for line in candidates:
            match = _FIGURE_CAPTION_RE.search(line.strip())
            if match:
                num = match.group(1)
                desc = match.group(2).strip().rstrip(".")
                return f"Figure {num}: {desc}" if desc else f"Figure {num}"
    return ""


def _add_figure_if_new(
    img_info, figure_dir: Path, seen: set[str], page_num: int,
    figures: list[ExtractedFigure], bbox=None, caption: str = "",
) -> None:
    resolved = _resolve_image_path(img_info, figure_dir)
    if resolved is None:
        return
    rp = str(resolved)
    if rp in seen:
        return
    seen.add(rp)
    figures.append(ExtractedFigure(
        image_path=rp,
        page_number=page_num,
        bbox=tuple(bbox) if bbox else None,
        caption=caption,
    ))


def _extract_figures_from_pages(
    page_chunks: list[dict],
    figure_dir: Path,
) -> list[ExtractedFigure]:
    figures: list[ExtractedFigure] = []
    seen_paths: set[str] = set()
    for page_data in page_chunks:
        page_num = page_data.get("metadata", {}).get("page", 0)
        page_text = page_data.get("text", "")
        for img_info in page_data.get("images", []):
            bbox = img_info.get("bbox") if isinstance(img_info, dict) else None
            _add_figure_if_new(img_info, figure_dir, seen_paths, page_num, figures, bbox)
        for match in _MD_IMAGE_RE.finditer(page_text):
            caption = _find_figure_caption(page_text, match.end())
            _add_figure_if_new(
                match.group(1), figure_dir, seen_paths, page_num, figures,
                caption=caption,
            )
    return figures


def _get_picture_boxes(page_data: dict) -> list[dict]:
    page_boxes = page_data.get("page_boxes", [])
    return [
        b for b in page_boxes
        if isinstance(b, dict) and b.get("class") == "picture"
    ]


def _is_nearby_caption_box(box: dict, pic_top: float, pic_bottom: float) -> bool:
    if not isinstance(box, dict) or box.get("class") != "caption":
        return False
    cap_bbox = box.get("bbox")
    if not cap_bbox or len(cap_bbox) < 4:
        return False
    cap_top = cap_bbox[1]
    return abs(cap_top - pic_bottom) < 40 or abs(cap_top - pic_top) < 40


def _parse_caption_text(raw: str) -> str:
    match = _FIGURE_CAPTION_RE.search(raw)
    if match:
        num = match.group(1)
        desc = match.group(2).strip().rstrip(".")
        return f"Figure {num}: {desc}" if desc else f"Figure {num}"
    return raw[:200] if raw else ""


def _extract_box_text(box: dict, page_text: str) -> str:
    pos = box.get("pos")
    if not pos or len(pos) < 2:
        return ""
    return page_text[pos[0]:pos[1]].strip()


def _find_caption_for_box(page_boxes: list[dict], picture_bbox: list, page_text: str) -> str:
    if not picture_bbox or len(picture_bbox) < 4:
        return ""
    pic_bottom = picture_bbox[3]
    pic_top = picture_bbox[1]

    for box in page_boxes:
        if not _is_nearby_caption_box(box, pic_top, pic_bottom):
            continue
        raw = _extract_box_text(box, page_text)
        if raw:
            return _parse_caption_text(raw)
    return ""


def _render_box(
    page, rect, page_num: int, idx: int, figure_dir: Path, caption: str = ""
) -> ExtractedFigure | None:
    bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
    img_name = f"page{page_num}_fig{idx}.{FIGURE_IMAGE_FORMAT}"
    img_path = figure_dir / img_name

    if not img_path.exists():
        pix = page.get_pixmap(clip=rect, dpi=FIGURE_IMAGE_DPI)
        pix.save(str(img_path))

    return ExtractedFigure(
        image_path=str(img_path),
        page_number=page_num,
        bbox=bbox,
        caption=caption,
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

    page_boxes = page_data.get("page_boxes", [])
    page_text = page_data.get("text", "")

    for idx, box in enumerate(picture_boxes):
        bbox = box.get("bbox")
        if not bbox or len(bbox) < 4:
            continue

        rect = pymupdf.Rect(bbox)
        if abs(rect.width * rect.height) / max(page_area, 1) < FIGURE_MIN_SIZE_RATIO:
            continue

        caption = _find_caption_for_box(page_boxes, bbox, page_text)
        fig = _render_box(page, rect, page_num, idx, figure_dir, caption=caption)
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
            page_boxes=page_data.get("page_boxes", []),
        ))
    return pages


def _validate_pdf(file_path: Path) -> tuple[int, dict]:
    import pymupdf

    doc = pymupdf.open(str(file_path))
    if doc.needs_pass:
        doc.close()
        raise PDFExtractionError(
            file_path.name,
            "PDF is password-protected. Please provide an unlocked version of the file.",
        )
    page_count = len(doc)
    pdf_metadata = dict(doc.metadata) if doc.metadata else {}
    doc.close()
    logger.info(f"PDF validated: {file_path.name}, {page_count} pages, meta keys={list(pdf_metadata.keys())}")
    return page_count, pdf_metadata


def _get_ocr_function():
    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr_engine = RapidOCR()

        def _ocr_wrapper(img_path, _lang=None, **_kwargs):
            result, _elapse = ocr_engine(img_path)
            if not result:
                return ""
            return "\n".join(line[1] for line in result if line and len(line) > 1)

        logger.info("RapidOCR loaded for scanned page fallback")
        return _ocr_wrapper
    except ImportError:
        logger.info("RapidOCR not available — OCR disabled for scanned pages")
        return None


def _run_layout_extraction(file_path: Path, figure_dir: Path) -> list[dict]:
    import pymupdf4llm

    kwargs = {
        "page_chunks": True,
        "write_images": True,
        "image_path": str(figure_dir),
        "image_format": FIGURE_IMAGE_FORMAT,
        "dpi": FIGURE_IMAGE_DPI,
        "force_text": True,
    }

    if _LAYOUT_MODE:
        kwargs["table_strategy"] = ""
    else:
        kwargs["image_size_limit"] = FIGURE_MIN_SIZE_RATIO

    ocr_fn = _get_ocr_function()
    if ocr_fn:
        kwargs["ocr"] = ocr_fn

    logger.info(
        f"Running {'layout' if _LAYOUT_MODE else 'legacy'} extraction on {file_path.name}"
    )

    return pymupdf4llm.to_markdown(str(file_path), **kwargs)


def _assemble_document(
    file_path: Path,
    page_chunks: list[dict],
    page_count: int,
    figure_dir: Path,
    pdf_metadata: dict | None = None,
) -> ExtractedDocument:
    md_text = "\n\n".join(p.get("text", "") for p in page_chunks)

    if not md_text or len(md_text.strip()) < 100:
        raise PDFExtractionError(
            file_path.name,
            "extracted text is too short — the PDF may be scanned or image-only",
        )

    figures = _extract_figures_from_pages(page_chunks, figure_dir)
    rendered = _render_missing_figures(file_path, page_chunks, figure_dir)
    existing_paths = {f.image_path for f in figures}
    for fig in rendered:
        if fig.image_path not in existing_paths:
            figures.append(fig)
            existing_paths.add(fig.image_path)
    all_figures = figures
    pages = _build_pages(page_chunks)

    text_tables = extract_tables_from_pages(pages)
    pdf_tables = [] if _LAYOUT_MODE else extract_tables_from_pdf(file_path)
    all_tables = merge_tables(text_tables, pdf_tables)

    all_formulas = extract_formulas_from_pages(pages)

    logger.info(
        f"Extracted {page_count} pages, {len(all_figures)} figures, "
        f"{len(all_tables)} tables, {len(all_formulas)} formulas "
        f"from {file_path.name} ({'layout' if _LAYOUT_MODE else 'legacy'} mode)"
    )

    return ExtractedDocument(
        markdown_text=md_text,
        page_count=page_count,
        filename=file_path.name,
        pages=pages,
        figures=all_figures,
        tables=all_tables,
        formulas=all_formulas,
        pdf_metadata=pdf_metadata,
        layout_mode=_LAYOUT_MODE,
    )


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFExtractionError(file_path.name, "file not found")

    try:
        page_count, pdf_metadata = _validate_pdf(file_path)
        figure_dir = _ensure_figure_dir(file_path)
        page_chunks = _run_layout_extraction(file_path, figure_dir)
        return _assemble_document(file_path, page_chunks, page_count, figure_dir, pdf_metadata)

    except PDFExtractionError:
        raise
    except Exception as exc:
        logger.error(f"PDF extraction failed for {file_path.name}: {exc}")
        raise PDFExtractionError(file_path.name, str(exc))

