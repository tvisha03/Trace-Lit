from pathlib import Path
import logging
import os
import re
from dataclasses import dataclass, field

try:
    import pymupdf.layout  # noqa: F401  # pylint: disable=unused-import
    _LAYOUT_MODE = True
except ImportError:
    _LAYOUT_MODE = False

import pymupdf

# Suppress MuPDF C-library stderr noise (e.g. zlib warnings on corrupt
# compressed streams) that can flood logs during PDF processing.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

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
    """Open and validate a PDF, returning page count and metadata.

    Calls ``doc.authenticate("")`` to unlock owner-password-restricted
    PDFs that don't require a user password but block text extraction
    via permission flags.
    """
    import pymupdf

    file_size = file_path.stat().st_size
    doc = pymupdf.open(str(file_path))

    # Unlock owner-password restrictions (no-op on unrestricted PDFs)
    if doc.is_encrypted:
        auth_result = doc.authenticate("")
        logger.info(
            f"PDF encrypted — authenticate('') returned {auth_result} "
            f"for {file_path.name}"
        )

    if doc.needs_pass:
        doc.close()
        raise PDFExtractionError(
            file_path.name,
            "PDF is password-protected. Please provide an unlocked version of the file.",
        )

    page_count = len(doc)
    pdf_metadata = dict(doc.metadata) if doc.metadata else {}
    permissions = doc.permissions

    # Quick first-page text probe for early diagnostics
    first_page_chars = 0
    if page_count > 0:
        first_page_chars = len(doc[0].get_text("text") or "")

    doc.close()

    logger.info(
        f"PDF validated: {file_path.name}, {page_count} pages, "
        f"size={file_size:,} bytes, permissions={permissions}, "
        f"first_page_chars={first_page_chars}, "
        f"resolved={file_path.resolve()}, "
        f"meta keys={list(pdf_metadata.keys())}"
    )
    if page_count == 0:
        try:
            raw = file_path.read_bytes()
            logger.error(
                f"ZERO-PAGE PDF: {file_path.name}, "
                f"disk_size={file_size:,}, content_size={len(raw):,}, "
                f"header={raw[:40]!r}, tail={raw[-40:]!r}"
            )
        except Exception:
            pass
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
    """Best-quality extraction via pymupdf4llm with layout analysis.

    Passes a pre-authenticated Document so that owner-password-
    restricted PDFs are unlocked before layout processing begins.
    """
    import pymupdf4llm

    # Open and authenticate before pymupdf4llm gets the document,
    # otherwise it calls pymupdf.open() without authentication.
    doc = _open_and_auth(file_path)

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

    return pymupdf4llm.to_markdown(doc, **kwargs)


def _open_and_auth(file_path: Path):
    """Open a PDF and authenticate with an empty owner password.

    Some publisher PDFs set owner restrictions that block text
    extraction.  Calling ``authenticate("")`` unlocks them when no
    user password is required.
    """
    import pymupdf

    doc = pymupdf.open(str(file_path))
    if doc.is_encrypted:
        doc.authenticate("")
    return doc


def _run_plain_text_extraction(file_path: Path) -> list[dict]:
    """Fallback: extract text page-by-page with pymupdf when layout mode fails.

    Some PDFs have corrupt compressed streams that break pymupdf4llm's
    layout analysis but still yield text via the simpler get_text() path.
    Also handles PDFs with null-character text (broken ToUnicode CMaps)
    by stripping non-printable characters.
    """
    doc = _open_and_auth(file_path)
    page_chunks: list[dict] = []
    raw_total = 0
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text") or ""
            raw_total += len(text)
            # Strip null and non-printable control characters that broken
            # ToUnicode CMaps produce — they look like 0-length after strip()
            cleaned = text.translate(_CTRL_CHAR_TABLE).strip()
            page_chunks.append({
                "metadata": {"page": page_num},
                "text": cleaned,
                "images": [],
                "tables": [],
                "toc_items": [],
                "page_boxes": [],
            })
    finally:
        doc.close()

    total_chars = sum(len(p["text"]) for p in page_chunks)
    logger.info(
        f"Plain-text fallback extracted {total_chars} chars "
        f"(raw={raw_total}) from {len(page_chunks)} pages of {file_path.name}"
    )
    return page_chunks


def _run_ocr_extraction(file_path: Path) -> list[dict]:
    """Last-resort fallback: render pages as images and OCR them.

    Used when both pymupdf4llm and plain get_text() fail — typically
    for scanned or image-only PDFs without an embedded text layer.
    """
    import tempfile

    ocr_fn = _get_ocr_function()
    if not ocr_fn:
        logger.warning("OCR not available — cannot extract text from image-only PDF")
        return []

    doc = _open_and_auth(file_path)
    page_chunks: list[dict] = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render page to image at moderate DPI for OCR accuracy vs speed
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")

            # Write temp image for OCR engine
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name

            try:
                text = ocr_fn(tmp_path) or ""
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            page_chunks.append({
                "metadata": {"page": page_num},
                "text": text.strip(),
                "images": [],
                "tables": [],
                "toc_items": [],
                "page_boxes": [],
            })
    finally:
        doc.close()

    total_chars = sum(len(p["text"]) for p in page_chunks)
    logger.info(
        f"OCR fallback extracted {total_chars} chars "
        f"from {len(page_chunks)} pages of {file_path.name}"
    )
    return page_chunks


_MIN_EXTRACTED_CHARS = 100

# Translation table that maps C0/C1 control characters (except common
# whitespace \t, \n, \r) to None — removes null bytes, BOM noise, and
# other invisible chars that broken ToUnicode CMaps produce.
_CTRL_CHAR_TABLE = str.maketrans(
    "",
    "",
    "".join(
        chr(c)
        for c in range(0, 32)
        if c not in (9, 10, 13)  # keep TAB, LF, CR
    )
    + "\x7f"  # DEL
    + "".join(chr(c) for c in range(0x80, 0xA0)),  # C1 controls
)


def _diagnose_empty_extraction(file_path: Path) -> None:
    """Log detailed per-page diagnostics when all extraction tiers fail.

    Re-opens the PDF with error display enabled so C-level messages are
    captured, then inspects fonts, images, raw text objects, and renders
    the first page for visual inspection.
    """
    import pymupdf

    # Temporarily re-enable C-library errors for diagnostic output
    pymupdf.TOOLS.mupdf_display_errors(True)
    try:
        doc = pymupdf.open(str(file_path))
        if doc.is_encrypted:
            doc.authenticate("")

        logger.error(
            f"ZERO-EXTRACTION DIAGNOSTIC for {file_path.name}: "
            f"pages={len(doc)}, encrypted={doc.is_encrypted}, "
            f"permissions={doc.permissions}"
        )

        for page_num in range(min(3, len(doc))):
            page = doc[page_num]
            raw_text = page.get_text("text") or ""
            words = page.get_text("words") or []
            fonts = page.get_fonts()
            images = page.get_images()
            raw_dict = page.get_text("rawdict") or {}
            blocks = raw_dict.get("blocks", [])
            text_blocks = [b for b in blocks if b.get("type") == 0]
            img_blocks = [b for b in blocks if b.get("type") == 1]

            # Check for null-heavy text
            null_count = raw_text.count("\x00")
            printable = sum(1 for c in raw_text if c.isprintable() or c in "\n\t\r")

            logger.error(
                f"  Page {page_num}: raw_len={len(raw_text)}, "
                f"null_chars={null_count}, printable={printable}, "
                f"words={len(words)}, fonts={len(fonts)}, "
                f"images={len(images)}, text_blocks={len(text_blocks)}, "
                f"img_blocks={len(img_blocks)}"
            )

            # Log first font names for encoding diagnosis
            if fonts:
                font_names = [f[3] for f in fonts[:5]]
                logger.error(f"    Fonts: {font_names}")

            # Show raw text sample (including non-printable chars)
            if raw_text:
                logger.error(f"    Raw text sample: {raw_text[:200]!r}")

        # Render first page and save diagnostic image
        if len(doc) > 0:
            pix = doc[0].get_pixmap(dpi=72)
            diag_dir = file_path.parent
            diag_path = diag_dir / f"_diag_{file_path.stem}_p0.png"
            pix.save(str(diag_path))
            logger.error(
                f"  Diagnostic render saved: {diag_path} "
                f"({pix.width}x{pix.height}, alpha={pix.alpha})"
            )

        doc.close()
    except Exception as exc:
        logger.error(f"Diagnostic inspection failed: {exc}")
    finally:
        pymupdf.TOOLS.mupdf_display_errors(False)


def _extract_with_fallback(file_path: Path, figure_dir: Path) -> list[dict]:
    """Three-tier extraction: layout → plain text → OCR.

    Each tier is tried only when the previous yields fewer than
    _MIN_EXTRACTED_CHARS characters of combined text.
    """
    # Tier 1: pymupdf4llm layout extraction (best quality)
    try:
        page_chunks = _run_layout_extraction(file_path, figure_dir)
        total = sum(len(p.get("text", "")) for p in page_chunks)
        if total >= _MIN_EXTRACTED_CHARS:
            return page_chunks
        logger.warning(
            f"Layout extraction yielded only {total} chars for "
            f"{file_path.name} — trying plain-text fallback"
        )
    except Exception as exc:
        logger.warning(
            f"Layout extraction failed for {file_path.name}: {exc} "
            f"— trying plain-text fallback"
        )

    # Tier 2: plain pymupdf get_text() (handles some corrupt-stream PDFs)
    try:
        page_chunks = _run_plain_text_extraction(file_path)
        total = sum(len(p.get("text", "")) for p in page_chunks)
        if total >= _MIN_EXTRACTED_CHARS:
            return page_chunks
        logger.warning(
            f"Plain-text extraction yielded only {total} chars for "
            f"{file_path.name} — trying OCR fallback"
        )
    except Exception as exc:
        logger.warning(
            f"Plain-text extraction failed for {file_path.name}: {exc} "
            f"— trying OCR fallback"
        )

    # Tier 3: render-to-image + OCR (handles scanned/image-only PDFs)
    try:
        page_chunks = _run_ocr_extraction(file_path)
        total = sum(len(p.get("text", "")) for p in page_chunks)
        if total >= _MIN_EXTRACTED_CHARS:
            logger.info(f"OCR fallback succeeded for {file_path.name}")
            return page_chunks
    except Exception as exc:
        logger.error(f"OCR extraction also failed for {file_path.name}: {exc}")

    # All tiers failed — run detailed diagnostics for debugging
    _diagnose_empty_extraction(file_path)
    return []

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
            "extracted text is too short — the PDF may be corrupted, "
            "scanned, or image-only.  Try re-downloading the paper from "
            "the publisher and uploading the fresh copy.",
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
        import os
        logger.error(
            f"PDF not found: {file_path} (cwd={os.getcwd()}, "
            f"resolved={file_path.resolve()})"
        )
        raise PDFExtractionError(file_path.name, "file not found")

    try:
        page_count, pdf_metadata = _validate_pdf(file_path)
        figure_dir = _ensure_figure_dir(file_path)
        page_chunks = _extract_with_fallback(file_path, figure_dir)
        return _assemble_document(file_path, page_chunks, page_count, figure_dir, pdf_metadata)

    except PDFExtractionError:
        raise
    except Exception as exc:
        logger.error(f"PDF extraction failed for {file_path.name}: {exc}")
        raise PDFExtractionError(file_path.name, str(exc))

