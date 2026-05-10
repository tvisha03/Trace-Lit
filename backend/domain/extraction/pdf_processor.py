from pathlib import Path
import logging
import re
from dataclasses import dataclass, field

try:
    import pymupdf.layout  # noqa: F401  # pylint: disable=unused-import
    _LAYOUT_MODE = True
except ImportError:
    _LAYOUT_MODE = False

logging.getLogger("pymupdf").setLevel(logging.ERROR)
logging.getLogger("pymupdf4llm").setLevel(logging.ERROR)

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

def _figure_file_prefix(file_path: Path) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9]+", "_", file_path.stem).strip("_")
    return safe_stem or "paper"

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
        # Always use 0-based indexing for internal consistency
        raw_page = page_data.get("metadata", {}).get("page", 0)
        page_num = raw_page - 1 if raw_page > 0 else 0
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
    page, rect, page_num: int, idx: int, figure_dir: Path, file_prefix: str, caption: str = ""
) -> ExtractedFigure | None:
    bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
    img_name = f"{file_prefix}_page{page_num}_fig{idx}.{FIGURE_IMAGE_FORMAT}"
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
    doc, page_data: dict, figure_dir: Path, file_prefix: str
) -> list[ExtractedFigure]:
    import pymupdf

    # Normalize to 0-based indexing
    raw_page = page_data.get("metadata", {}).get("page", 0)
    page_num = raw_page - 1 if raw_page > 0 else 0
    picture_boxes = _get_picture_boxes(page_data)

    if not picture_boxes or page_num >= len(doc):
        return []

    # doc index is 0-based
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
        fig = _render_box(page, rect, page_num, idx, figure_dir, file_prefix, caption=caption)
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
    file_prefix = _figure_file_prefix(file_path)
    doc = pymupdf.open(str(file_path))
    try:
        for page_data in page_chunks:
            rendered.extend(_render_page_figures(doc, page_data, figure_dir, file_prefix))
    finally:
        doc.close()

    return rendered

def _build_pages(page_chunks: list[dict]) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    for i, page_data in enumerate(page_chunks, start=0):
        meta = page_data.get("metadata", {})
        # Robustly determine page number:
        # We always want 0-based internal indexing.
        # pymupdf4llm often provides 1-based "page" in metadata.
        raw_page = meta.get("page")
        try:
            if raw_page is not None:
                p_num = int(raw_page)
                # If it looks like it was 1-based (starts at 1 or more), normalize to 0-based.
                # If it's already 0, it's 0-based.
                # This handles both pymupdf4llm (1-based) and our fallbacks (0-based).
                page_number = p_num - 1 if p_num > 0 else 0
            else:
                page_number = i
        except (ValueError, TypeError):
            page_number = i

        pages.append(ExtractedPage(
            page_number=page_number,
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

def _build_layout_kwargs(write_images: bool, figure_dir: Path) -> dict:
    kwargs: dict = {
        "page_chunks": True,
        "write_images": write_images,
        "force_text": True,
    }
    if write_images:
        kwargs["image_path"] = str(figure_dir)
        kwargs["image_format"] = FIGURE_IMAGE_FORMAT
        kwargs["dpi"] = FIGURE_IMAGE_DPI
    if _LAYOUT_MODE:
        kwargs["table_strategy"] = ""
    else:
        kwargs["image_size_limit"] = FIGURE_MIN_SIZE_RATIO
    return kwargs

def _run_layout_extraction(file_path: Path, figure_dir: Path) -> list[dict]:
    import pymupdf4llm

    kwargs = _build_layout_kwargs(write_images=True, figure_dir=figure_dir)
    ocr_fn = _get_ocr_function()
    if ocr_fn:
        kwargs["ocr"] = ocr_fn

    chunks = pymupdf4llm.to_markdown(str(file_path), **kwargs)
    # Normalize metadata to 0-based indexing immediately
    for chunk in chunks:
        if "metadata" in chunk and "page" in chunk["metadata"]:
            p = chunk["metadata"]["page"]
            chunk["metadata"]["page"] = p - 1 if p > 0 else 0
    return chunks


def _run_layout_extraction_no_images(file_path: Path, figure_dir: Path) -> list[dict]:
    import pymupdf4llm

    kwargs = _build_layout_kwargs(write_images=False, figure_dir=figure_dir)
    ocr_fn = _get_ocr_function()
    if ocr_fn:
        kwargs["ocr"] = ocr_fn

    chunks = pymupdf4llm.to_markdown(str(file_path), **kwargs)
    # Normalize metadata to 0-based indexing immediately
    for chunk in chunks:
        if "metadata" in chunk and "page" in chunk["metadata"]:
            p = chunk["metadata"]["page"]
            chunk["metadata"]["page"] = p - 1 if p > 0 else 0
    return chunks


def _run_plain_text_extraction(file_path: Path) -> list[dict]:
    import pymupdf

    logger.info(f"Running plain-text fallback extraction on {file_path.name}")
    doc = pymupdf.open(str(file_path))
    page_chunks: list[dict] = []
    try:
        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            page_chunks.append({
                # Use 0-based indexing for internal consistency; 
                # _build_pages will convert to 1-based for the database.
                "metadata": {"page": page_num},
                "text": text,
                "tables": [],
                "images": [],
                "toc_items": [],
                "page_boxes": [],
            })
    finally:
        doc.close()

    logger.info(
        f"Plain-text fallback extracted {len(page_chunks)} pages from {file_path.name}"
    )
    return page_chunks

def _build_page_text_map(page_chunks: list[dict]) -> dict[int, str]:
    return {
        chunk.get("metadata", {}).get("page", i): chunk.get("text", "")
        for i, chunk in enumerate(page_chunks)
    }

def _try_render_image_on_page(
    page,
    idx: int,
    img_info: dict,
    page_num: int,
    page_area: float,
    figure_dir: Path,
    file_prefix: str,
) -> ExtractedFigure | None:
    import pymupdf
    import re

    bbox = img_info.get("bbox")
    if not bbox or len(bbox) < 4:
        return None

    rect = pymupdf.Rect(bbox)
    if abs(rect.width * rect.height) / max(page_area, 1) < FIGURE_MIN_SIZE_RATIO:
        return None

    img_name = f"{file_prefix}_page{page_num}_rendered{idx}.{FIGURE_IMAGE_FORMAT}"
    img_path = figure_dir / img_name

    try:
        if not img_path.exists():
            pix = page.get_pixmap(clip=rect, dpi=FIGURE_IMAGE_DPI)
            pix.save(str(img_path))
    except Exception as exc:  # pragma: no cover
        logger.debug(f"Pixmap render failed for page {page_num} img {idx}: {exc}")
        return None

    caption = ""
    caption_bbox = None
    inline_references = []
    try:
        blocks = page.get_text("blocks")
        for b in blocks:
            if len(b) >= 5 and isinstance(b[4], str):
                bx0, by0, bx1, by1, btext, *_ = b
                is_near_y = (by0 >= bbox[3] - 10 and by0 <= bbox[3] + 50) or (by1 >= bbox[1] - 50 and by1 <= bbox[1] + 10)
                if is_near_y and re.match(r'^\s*(figure|fig\.?)\s*\d+[:\.]?', btext, re.IGNORECASE):
                    caption = btext.strip()
                    caption_bbox = (bx0, by0, bx1, by1)
                    break
    except Exception:
        pass

    if not caption_bbox:
        caption_bbox = (bbox[0], bbox[3] + 5, bbox[2], bbox[3] + 35)
        caption = f"Figure on page {page_num}"

    fig_num = 1
    m = re.search(r'\d+', caption)
    if m:
        fig_num = int(m.group(0))

    try:
        # Scan page for references like "Figure N"
        words = page.get_text("words")
        for w in words:
            if len(w) >= 5 and isinstance(w[4], str):
                wx0, wy0, wx1, wy1, wtext, *_ = w
                if re.match(rf'\b(fig\.|figure)\s*{fig_num}\b', wtext, re.IGNORECASE):
                    inline_references.append({
                        "page": page_num,
                        "bbox": (wx0, wy0, wx1, wy1),
                        "text": wtext
                    })
    except Exception:
        pass

    bbox_dict = {
        "source_type": "figure",
        "figure_id": f"figure_{page_num}_{idx}",
        "page": page_num,
        "figure_number": fig_num,
        "image_bbox": tuple(bbox),
        "caption_bbox": caption_bbox,
        "caption_text": caption,
        "inline_references": inline_references,
    }

    return ExtractedFigure(
        image_path=str(img_path),
        page_number=page_num,
        bbox=bbox_dict,
        caption=caption,
    )

def _render_figures_by_rendering(
    file_path: Path,
    figure_dir: Path,
    page_chunks: list[dict],
) -> list[ExtractedFigure]:
    import pymupdf

    file_prefix = _figure_file_prefix(file_path)
    doc = pymupdf.open(str(file_path))
    figures: list[ExtractedFigure] = []
    try:
        for page_num_0, page in enumerate(doc):
            page_num = page_num_0
            page_area = abs(page.rect.width * page.rect.height)
            try:
                image_infos = page.get_image_info()
            except Exception as exc:  # pragma: no cover
                logger.debug(f"get_image_info failed on page {page_num}: {exc}")
                continue

            for idx, img_info in enumerate(image_infos):
                fig = _try_render_image_on_page(
                    page, idx, img_info, page_num, page_area, figure_dir, file_prefix,
                )
                if fig:
                    figures.append(fig)
    finally:
        doc.close()

    logger.info(
        f"Render-based figure extraction found {len(figures)} figures in {file_path.name}"
    )
    return figures

def _merge_figures(
    base: list[ExtractedFigure],
    supplement: list[ExtractedFigure],
) -> list[ExtractedFigure]:
    # Map by image_path to identify duplicates and preserve metadata
    merged_map: dict[str, ExtractedFigure] = {f.image_path: f for f in base}
    
    for fig in supplement:
        if fig.image_path not in merged_map:
            merged_map[fig.image_path] = fig
        else:
            # If duplicate, prefer the version that has a bbox
            existing = merged_map[fig.image_path]
            if not existing.bbox and fig.bbox:
                merged_map[fig.image_path] = fig
                
    return list(merged_map.values())

def _assemble_document(
    file_path: Path,
    page_chunks: list[dict],
    page_count: int,
    figure_dir: Path,
    pdf_metadata: dict | None = None,
    supplement_figures: list[ExtractedFigure] | None = None,
) -> ExtractedDocument:
    md_text = "\n\n".join(p.get("text", "") for p in page_chunks)

    if not md_text or len(md_text.strip()) < 100:
        raise PDFExtractionError(
            file_path.name,
            "extracted text is too short — the PDF may be scanned or image-only",
        )

    figures = _extract_figures_from_pages(page_chunks, figure_dir)
    rendered = _render_missing_figures(file_path, page_chunks, figure_dir)
    all_figures = _merge_figures(figures, rendered)
    if supplement_figures:
        all_figures = _merge_figures(all_figures, supplement_figures)
    pages = _build_pages(page_chunks)

    text_tables = extract_tables_from_pages(pages)
    try:
        pdf_tables = extract_tables_from_pdf(file_path)
    except Exception as exc:
        logger.warning(f"Native PDF table extraction failed for {file_path.name}: {exc}")
        pdf_tables = []
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

def _is_too_short_error(err: PDFExtractionError) -> bool:
    return "too short" in str(err)

def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFExtractionError(file_path.name, "file not found")

    page_count, pdf_metadata = _validate_pdf(file_path)
    figure_dir = _ensure_figure_dir(file_path)

    # Tier 1: full layout extraction with images (best quality).
    try:
        page_chunks = _run_layout_extraction(file_path, figure_dir)
        return _assemble_document(file_path, page_chunks, page_count, figure_dir, pdf_metadata)
    except PDFExtractionError as err:
        if not _is_too_short_error(err):
            raise
        logger.warning(
            f"Tier 1 extraction too short for {file_path.name} — retrying without images"
        )
    except Exception as exc:
        logger.warning(
            f"Tier 1 extraction failed for {file_path.name}: {exc} — retrying without images"
        )

    # Tier 2: layout extraction without image rendering, skipping zlib-compressed
    # image streams that cause MuPDF errors.  Tables, formulas, and sections are
    # still extracted via pymupdf4llm.  Figures are recovered separately through
    # page.get_image_info() + page.get_pixmap(clip=rect) — both are pure render
    # operations that never touch raw compressed streams, so they succeed even
    # when zlib decompression fails.  Full functionality is preserved.
    try:
        page_chunks = _run_layout_extraction_no_images(file_path, figure_dir)
        rendered_figs = _render_figures_by_rendering(file_path, figure_dir, page_chunks)
        return _assemble_document(
            file_path, page_chunks, page_count, figure_dir, pdf_metadata,
            supplement_figures=rendered_figs,
        )
    except PDFExtractionError as err:
        if not _is_too_short_error(err):
            raise
        logger.warning(
            f"Tier 2 extraction too short for {file_path.name} — falling back to plain text"
        )
    except Exception as exc:
        logger.warning(
            f"Tier 2 extraction failed for {file_path.name}: {exc} — falling back to plain text"
        )

    # Tier 3: plain-text fallback — no tables/figures/formulas, but recovers
    # text from PDFs that have heavily corrupted or missing image streams.
    return _extract_pdf_plain_fallback(file_path, page_count, figure_dir, pdf_metadata)

def _extract_pdf_plain_fallback(
    file_path: Path,
    page_count: int,
    figure_dir: Path,
    pdf_metadata: dict | None,
) -> ExtractedDocument:
    try:
        page_chunks = _run_plain_text_extraction(file_path)
        return _assemble_document(file_path, page_chunks, page_count, figure_dir, pdf_metadata)
    except PDFExtractionError:
        raise
    except Exception as fallback_exc:
        logger.error(f"Plain-text fallback also failed for {file_path.name}: {fallback_exc}")
        raise PDFExtractionError(file_path.name, str(fallback_exc)) from fallback_exc

