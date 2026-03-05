
from datetime import datetime
from pathlib import Path

from shared.logger import get_logger
from shared.errors import PDFExportError
from shared.utils.export_text import clean_for_export, sanitize_for_pdf, format_structured_text
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_MAX_TEXT_CHARS = 50_000
_DATE_FMT = "%B %d, %Y"

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

def _havf_confidence_color(confidence: str) -> tuple[int, int, int]:
    if confidence == "high":
        return (34, 139, 34)
    if confidence == "medium":
        return (204, 153, 0)
    return (204, 51, 51)

def _add_page_header(pdf, title: str) -> None:
    pdf.set_font("Helvetica", "I", 7)
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
    pdf.set_font("Helvetica", "B", 10)
    if role == "ASSISTANT":
        pdf.set_text_color(0, 51, 153)
    else:
        pdf.set_text_color(80, 80, 80)
    pdf.cell(w=0, h=6, text=f"[{role}]", ln=True)
    pdf.set_text_color(0, 0, 0)

def _render_havf_results(pdf, havf_results: list[dict]) -> None:
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 8)
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
        pdf.set_font("Helvetica", "B", 7)

        badge = f"  [{confidence.upper()}] ({score:.0%})"
        if paragraph_id:
            badge += f"  [{paragraph_id}]"
        if chunk_type and chunk_type != "text":
            badge += f"  ({chunk_type})"
        pdf.cell(w=0, h=3.5, text=badge, ln=True)

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(w=0, h=3.5, text=f'    "{claim}"')

    pdf.set_text_color(0, 0, 0)

def _render_message_separator(pdf) -> None:
    pdf.set_draw_color(220, 220, 220)
    y = pdf.get_y()
    pdf.line(20, y, 190, y)
    pdf.ln(3)

def _setup_pdf_title_and_date(pdf, title: str) -> None:
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(
        w=0, h=10,
        text=sanitize_for_pdf(_truncate_text(title, 200)),
        ln=True, align="C",
    )
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        w=0, h=5,
        text=f"Exported on {datetime.now().strftime(_DATE_FMT)}",
        ln=True, align="C",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

def _add_papers_compared_section(pdf, paper_titles: list[str]) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(w=0, h=7, text="Papers Compared:", ln=True)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 9)
    for i, paper in enumerate(paper_titles, start=1):
        truncated = sanitize_for_pdf(_truncate_text(paper, 200))
        safe = _break_long_words(truncated)
        pdf.multi_cell(w=0, h=5, text=f"  {i}. {safe}")
    pdf.ln(3)

def _render_message_block(pdf, msg: dict) -> None:
    role = msg.get("role", "user").upper()
    content = msg.get("content", "")
    havf_results = msg.get("havf_results") or []

    _render_message_role(pdf, role)
    pdf.set_font("Helvetica", "", 9)
    safe_content = _break_long_words(clean_for_export(content))
    pdf.multi_cell(w=0, h=4.5, text=safe_content)

    if havf_results:
        _render_havf_results(pdf, havf_results)

    _render_message_separator(pdf)

def export_chat_to_pdf(
    session_title: str,
    messages: list[dict],
    output_path: str | Path,
) -> Path:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise PDFExportError("fpdf2 library not installed") from e

    output_path = Path(output_path)

    try:
        with timer("PDF generation"):
            pdf = FPDF(format="A4", unit="mm")
            pdf.set_margins(left=15, top=15, right=15)
            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.add_page()

            _setup_pdf_title_and_date(pdf, session_title)

            pdf.set_draw_color(180, 180, 180)
            y = pdf.get_y()
            pdf.line(15, y, 195, y)
            pdf.ln(5)

            for msg in messages:
                _render_message_block(pdf, msg)

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
    output_path: str | Path,
) -> Path:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise PDFExportError("fpdf2 library not installed") from e

    output_path = Path(output_path)

    try:
        pdf = FPDF(format="A4", unit="mm")
        pdf.set_margins(left=15, top=15, right=15)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        _setup_pdf_title_and_date(pdf, title)
        _add_papers_compared_section(pdf, paper_titles)

        pdf.set_draw_color(180, 180, 180)
        y = pdf.get_y()
        pdf.line(15, y, 195, y)
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w=0, h=7, text="Comparison Analysis:", ln=True)
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)

        cleaned = sanitize_for_pdf(format_structured_text(comparison_content))
        for paragraph in cleaned.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            safe = _break_long_words(paragraph)
            try:
                pdf.multi_cell(w=0, h=4.5, text=safe)
            except Exception:
                pdf.multi_cell(w=0, h=4.5, text=safe[:500] + "...")
            pdf.ln(2)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path

