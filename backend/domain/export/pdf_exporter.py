
from datetime import datetime
from pathlib import Path
from typing import Any
import importlib

from shared.logger import get_logger
from shared.errors import PDFExportError
from shared.utils.export_media import prepare_cited_assets
from shared.utils.export_text import build_export_blocks, inline_tokens_to_text, sanitize_for_pdf, format_structured_text, shorten_paragraph_id
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_MAX_TEXT_CHARS = 50_000
_DATE_FMT = "%B %d, %Y"
_ACCENT_RGB = (47, 79, 111)
_ACCENT_LIGHT_RGB = (232, 238, 244)
_USER_RGB = (95, 95, 95)
_ASSISTANT_RGB = (32, 76, 165)
_PDF_FONT_CANDIDATES = [
    ("TraceLitUnicode", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("TraceLitUnicode", "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
    ("TraceLitUnicode", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
]

def _truncate_text(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text

def _break_long_words(text: str, max_word: int = 80) -> str:

    parts: list[str] = []
    for token in text.split(" "):
        while len(token) > max_word:
            parts.append(token[:max_word])
            token = token[max_word:]
        parts.append(token)
    return " ".join(parts)


def _configure_pdf_fonts(pdf) -> str:
    for family, regular, bold in _PDF_FONT_CANDIDATES:
        regular_path = Path(regular)
        if not regular_path.exists():
            continue
        try:
            pdf.add_font(family, "", fname=str(regular_path))
            if Path(bold).exists():
                pdf.add_font(family, "B", fname=bold)
            return family
        except Exception:
            continue
    return "Helvetica"


def _set_font(pdf, style: str, size: int) -> None:
    family = getattr(pdf, "trace_font_family", "Helvetica")
    try:
        pdf.set_font(family, style=style, size=size)
    except Exception:
        pdf.set_font("Helvetica", style=style, size=size)


def _safe_multi_cell(pdf, text: str, line_height: float = 4.5) -> None:
    pdf.set_x(pdf.l_margin)
    safe_text = text or ""
    try:
        pdf.multi_cell(w=0, h=line_height, text=safe_text)
    except Exception:
        fallback = _break_long_words(sanitize_for_pdf(safe_text), max_word=24)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w=0, h=line_height, text=fallback)


def _write_flowing_text(pdf, text: str, line_height: float = 4.5) -> None:
    pdf.set_x(pdf.l_margin)
    safe_text = sanitize_for_pdf(text or "")
    try:
        pdf.write(line_height, safe_text)
    except Exception:
        _safe_multi_cell(pdf, safe_text, line_height)


def _prepare_landscape_pdf() -> Any:
    FPDF = importlib.import_module("fpdf").FPDF
    pdf = FPDF(orientation="L", format="A4", unit="mm")
    pdf.set_margins(left=10, top=12, right=10)
    pdf.set_auto_page_break(auto=True, margin=15)
    setattr(pdf, "trace_font_family", _configure_pdf_fonts(pdf))
    pdf.add_page()
    return pdf

def _havf_confidence_color(confidence: str) -> tuple[int, int, int]:
    if confidence == "high":
        return (34, 139, 34)
    if confidence == "medium":
        return (204, 153, 0)
    return (204, 51, 51)

def _add_page_header(pdf, title: str) -> None:
    _set_font(pdf, "I", 7)
    pdf.set_text_color(140, 140, 140)
    date_str = datetime.now().strftime(_DATE_FMT)
    header_text = f"TraceLit  |  {sanitize_for_pdf(_truncate_text(title, 80))}  |  {date_str}"
    pdf.cell(w=0, h=4, text=header_text, ln=True, align="C")
    pdf.set_draw_color(200, 200, 200)
    y = pdf.get_y()
    pdf.line(15, y, 195, y)
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)

def _render_message_role(pdf, role: str) -> None:
    role_color = _ASSISTANT_RGB if role == "ASSISTANT" else _USER_RGB
    _set_font(pdf, "B", 9)
    pdf.set_fill_color(*role_color)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(w=28, h=6, text=f" {role} ", ln=True, fill=True)
    pdf.ln(1)
    pdf.set_text_color(0, 0, 0)

def _render_havf_results(pdf, havf_results: list[dict]) -> None:
    pdf.ln(1)
    _set_font(pdf, "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(w=0, h=4, text="Citation Verification:", ln=True)

    for result in havf_results:
        confidence = result.get("confidence", "low")
        raw_claim = result.get("claim", "")

        if len(raw_claim) > 500:
            raw_claim = raw_claim[:500].rsplit(" ", 1)[0] + "..."
        claim = sanitize_for_pdf(raw_claim)
        paragraph_id = result.get("paragraph_id", "")
        chunk_type = result.get("chunk_type", "")
        score = result.get("score", 0)

        cr, cg, cb = _havf_confidence_color(confidence)
        pdf.set_text_color(cr, cg, cb)
        _set_font(pdf, "B", 7)

        badge = f"  [{confidence.upper()}] ({score:.0%})"
        if paragraph_id:
            badge += f"  [{shorten_paragraph_id(paragraph_id)}]"
        if chunk_type and chunk_type != "text":
            badge += f"  ({chunk_type})"
        pdf.cell(w=0, h=3.5, text=badge, ln=True)

        _set_font(pdf, "", 7)
        pdf.set_text_color(60, 60, 60)
        _safe_multi_cell(pdf, f'    "{_break_long_words(claim, max_word=48)}"', 3.5)

    pdf.set_text_color(0, 0, 0)

def _render_message_separator(pdf) -> None:
    pdf.set_draw_color(210, 217, 224)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)

def _setup_pdf_title_and_date(pdf, title: str) -> None:
    pdf.set_fill_color(*_ACCENT_RGB)
    pdf.set_text_color(255, 255, 255)
    _set_font(pdf, "B", 16)
    pdf.cell(w=0, h=11, text=sanitize_for_pdf(_truncate_text(title, 200)), ln=True, align="C", fill=True)
    pdf.set_fill_color(*_ACCENT_LIGHT_RGB)
    _set_font(pdf, "", 9)
    pdf.set_text_color(70, 70, 70)
    pdf.cell(w=0, h=7, text=f"Exported on {datetime.now().strftime(_DATE_FMT)}", ln=True, align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

def _add_papers_compared_section(pdf, paper_titles: list[str]) -> None:
    _set_font(pdf, "B", 12)
    pdf.cell(w=0, h=7, text="Papers Compared:", ln=True)
    pdf.ln(1)
    _set_font(pdf, "", 9)
    for i, paper in enumerate(paper_titles, start=1):
        truncated = sanitize_for_pdf(_truncate_text(paper, 200))
        safe = _break_long_words(truncated)
        _safe_multi_cell(pdf, f"  {i}. {safe}", 5)
    pdf.ln(3)

def _render_message_block(pdf, msg: dict) -> None:
    role = msg.get("role", "user").upper()
    content = msg.get("content", "")
    havf_results = msg.get("havf_results") or []

    _render_message_role(pdf, role)
    _render_blocks_pdf(pdf, build_export_blocks(content))

    if havf_results:
        _render_havf_results(pdf, havf_results)

    _render_message_separator(pdf)


def _render_table_as_sections(pdf, headers: list[str], rows: list[list[str]]) -> None:
    for row in rows:
        for index, value in enumerate(row):
            if index >= len(headers):
                continue
            label = sanitize_for_pdf(headers[index])
            body = sanitize_for_pdf(_break_long_words(value, max_word=42))
            _set_font(pdf, "B", 9)
            _safe_multi_cell(pdf, label, 4.2)
            _set_font(pdf, "", 9)
            _safe_multi_cell(pdf, body, 4.2)
        pdf.ln(1)


def _render_table_grid(pdf, headers: list[str], rows: list[list[str]]) -> None:
    if not headers:
        return

    normalized_rows = []
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        normalized_rows.append([sanitize_for_pdf(format_structured_text(cell)) for cell in padded[:len(headers)]])

    available_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_width = available_width / max(len(headers), 1)
    _set_font(pdf, "", 8)
    try:
        with pdf.table(
            col_widths=[col_width] * len(headers),
            line_height=4.2,
            text_align="LEFT",
            borders_layout="ALL",
            width=available_width,
        ) as table:
            header_row = table.row()
            for header in headers:
                header_row.cell(sanitize_for_pdf(header))
            for row in normalized_rows:
                body_row = table.row()
                for cell in row:
                    body_row.cell(cell)
    except Exception:
        _render_table_as_sections(pdf, headers, rows)


def _render_landscape_table(pdf, headers: list[str], rows: list[list[str]]) -> None:
    normalized_rows = []
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        normalized_rows.append([sanitize_for_pdf(format_structured_text(cell)) for cell in padded[:len(headers)]])

    available_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_width = available_width / max(len(headers), 1)
    _set_font(pdf, "", 8)
    with pdf.table(
        col_widths=[col_width] * len(headers),
        line_height=4.2,
        text_align="LEFT",
        borders_layout="SINGLE_TOP_LINE",
        width=available_width,
    ) as table:
        header_row = table.row()
        for header in headers:
            header_row.cell(sanitize_for_pdf(header))
        for row in normalized_rows:
            body_row = table.row()
            for cell in row:
                body_row.cell(cell)


def _render_blocks_pdf(pdf, blocks: list) -> None:
    for block in blocks:
        if block.kind == "heading":
            size = max(10, 15 - min(block.level, 4))
            _set_font(pdf, "B", size)
            _safe_multi_cell(pdf, sanitize_for_pdf(block.text), 5)
            pdf.ln(1)
        elif block.kind == "bullet":
            _set_font(pdf, "", 9)
            bullet_text = sanitize_for_pdf(_break_long_words(block.text, max_word=42))
            _write_flowing_text(pdf, f"- {bullet_text}", 4.5)
            pdf.ln(4.5)
        elif block.kind == "table":
            _render_table_grid(pdf, block.headers, block.rows)
        else:
            _set_font(pdf, "", 9)
            paragraph = sanitize_for_pdf(_break_long_words(inline_tokens_to_text(block.tokens), max_word=42))
            _write_flowing_text(pdf, paragraph, 4.5)
            pdf.ln(5.5)


def _render_cited_assets_pdf(pdf, cited_assets: list[dict]) -> None:
    if not cited_assets:
        return

    if pdf.page_no() > 0:
        pdf.add_page()
    pdf.set_fill_color(*_ACCENT_LIGHT_RGB)
    _set_font(pdf, "B", 12)
    pdf.cell(w=0, h=8, text="Cited Figures, Tables, and Formulas", ln=True, fill=True)
    pdf.ln(2)

    for asset in cited_assets:
        label = f"[{asset.get('citation_id', '')}] {str(asset.get('chunk_type', '')).title()}"
        meta_parts = [str(asset.get("paper_title", ""))]
        if asset.get("page_number"):
            meta_parts.append(f"page {asset.get('page_number')}")
        if asset.get("section_title"):
            meta_parts.append(str(asset.get("section_title")))

        _set_font(pdf, "B", 10)
        _safe_multi_cell(pdf, sanitize_for_pdf(label), 5)
        if meta_parts:
            _set_font(pdf, "I", 8)
            _safe_multi_cell(pdf, sanitize_for_pdf(" | ".join(part for part in meta_parts if part)), 4)

        chunk_type = str(asset.get("chunk_type", "")).lower()
        if chunk_type == "table" and asset.get("table_headers"):
            description = str(asset.get("description") or "").strip()
            if description:
                _render_blocks_pdf(pdf, build_export_blocks(description))
            _render_table_grid(
                pdf,
                list(asset.get("table_headers") or []),
                [list(row) for row in asset.get("table_rows") or []],
            )
        else:
            description = str(asset.get("description") or asset.get("raw_content") or asset.get("content", "")).strip()
            if description:
                _render_blocks_pdf(pdf, build_export_blocks(description))

            image_path = asset.get("image_path")
            if image_path and Path(image_path).exists():
                try:
                    pdf.image(str(image_path), w=160)
                    pdf.ln(2)
                except Exception:
                    pass
            elif chunk_type == "formula" and asset.get("formula_text"):
                _set_font(pdf, "", 9)
                _safe_multi_cell(pdf, sanitize_for_pdf(str(asset.get("formula_text"))), 4.5)

        _render_message_separator(pdf)

def export_chat_to_pdf(
    session_title: str,
    messages: list[dict],
    cited_assets: list[dict] | None,
    output_path: str | Path,
) -> Path:
    try:
        importlib.import_module("fpdf")
    except ImportError as e:
        raise PDFExportError("fpdf2 library not installed") from e

    output_path = Path(output_path)
    cited_assets = prepare_cited_assets(cited_assets or [], output_path.parent)

    try:
        with timer("PDF generation"):
            FPDF = importlib.import_module("fpdf").FPDF
            pdf = FPDF(format="A4", unit="mm")
            pdf.set_margins(left=15, top=15, right=15)
            pdf.set_auto_page_break(auto=True, margin=20)
            setattr(pdf, "trace_font_family", _configure_pdf_fonts(pdf))
            pdf.add_page()

            _setup_pdf_title_and_date(pdf, session_title)

            pdf.set_draw_color(180, 180, 180)
            y = pdf.get_y()
            pdf.line(15, y, 195, y)
            pdf.ln(5)

            for msg in messages:
                _render_message_block(pdf, msg)

            _render_cited_assets_pdf(pdf, cited_assets)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported chat PDF to {output_path.name}")
    return output_path

def export_comparison_to_pdf(
    title: str,
    comparison_content: str,
    paper_titles: list[str],
    comparison_table: list[dict] | None,
    cited_assets: list[dict] | None,
    output_path: str | Path,
) -> Path:
    try:
        importlib.import_module("fpdf")
    except ImportError as e:
        raise PDFExportError("fpdf2 library not installed") from e

    output_path = Path(output_path)
    cited_assets = prepare_cited_assets(cited_assets or [], output_path.parent)

    try:
        pdf = _prepare_landscape_pdf()

        _setup_pdf_title_and_date(pdf, title)
        _add_papers_compared_section(pdf, paper_titles)

        pdf.set_draw_color(180, 180, 180)
        y = pdf.get_y()
        pdf.line(15, y, 195, y)
        pdf.ln(4)

        _set_font(pdf, "B", 12)
        pdf.cell(w=0, h=7, text="Comparison Analysis:", ln=True)
        pdf.ln(1)
        if comparison_table:
            headers = ["Dimension", *paper_titles, "Synthesis"]
            rows = []
            for row in comparison_table:
                rows.append([
                    str(row.get("dimension", "")),
                    *[format_structured_text(str(cell.get("content", ""))) for cell in row.get("cells", [])],
                    format_structured_text(str(row.get("synthesis", ""))),
                ])
            _render_landscape_table(pdf, headers, rows)
        else:
            _render_blocks_pdf(pdf, build_export_blocks(comparison_content))

        _render_cited_assets_pdf(pdf, cited_assets)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path

