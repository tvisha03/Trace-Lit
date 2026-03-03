
from pathlib import Path
from html import escape

from shared.logger import get_logger
from shared.errors import PDFExportError
from shared.utils.time_utils import timer

logger = get_logger(__name__)

def _truncate_text(text: str, max_chars: int = 10000) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text

def _havf_confidence_color(confidence: str) -> tuple[int, int, int]:
    if confidence == "high":
        return (86, 184, 112)
    if confidence == "medium":
        return (244, 162, 97)
    return (231, 111, 81)

def _render_message_role(pdf, role: str) -> None:
    """Render the role header with appropriate color."""
    pdf.set_font("Helvetica", "B", 10)
    if role == "ASSISTANT":
        pdf.set_text_color(0, 0, 139)
    else:
        pdf.set_text_color(60, 60, 60)
    pdf.cell(w=0, h=5, text=f"[{role}]", ln=True)
    pdf.set_text_color(0, 0, 0)

def _render_havf_results(pdf, havf_results: list[dict]) -> None:
    """Render verification results for a message."""
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(w=0, h=4, text="Verification:", ln=True)

    for result in havf_results:
        confidence = result.get("confidence", "low")
        claim = result.get("claim", "")[:120]
        paragraph_id = result.get("paragraph_id", "")
        score = result.get("score", 0)

        cr, cg, cb = _havf_confidence_color(confidence)
        pdf.set_text_color(cr, cg, cb)
        pdf.set_font("Helvetica", "B", 8)

        line = f"  {confidence.upper()} ({score:.2f})"
        if paragraph_id:
            line += f" [{paragraph_id}]"
        line += f" — \"{claim}\""
        pdf.multi_cell(w=0, h=3.5, text=line)

    pdf.set_text_color(0, 0, 0)

def _render_message_block(pdf, msg: dict) -> None:
    """Render a single message and its verification results."""
    role = msg.get("role", "user").upper()
    content = msg.get("content", "")
    havf_results = msg.get("havf_results") or []

    _render_message_role(pdf, role)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(w=0, h=4, text=escape(content))

    if havf_results:
        _render_havf_results(pdf, havf_results)

    pdf.ln(2)

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
            pdf.add_page()

            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(w=0, h=10, text=_truncate_text(session_title, 200), ln=True, align="C")
            pdf.ln(3)

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
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(w=0, h=10, text=_truncate_text(title, 200), ln=True, align="C")

        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(w=0, h=6, text="Papers Compared:", ln=True)
        pdf.set_font("Helvetica", "", 9)

        for paper in paper_titles:
            truncated_paper = _truncate_text(paper, 200)
            pdf.cell(w=5, h=4, text="•")
            pdf.multi_cell(w=0, h=4, text=escape(truncated_paper))

        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(w=0, h=6, text="Comparison:", ln=True)
        pdf.set_font("Helvetica", "", 9)

        pdf.multi_cell(w=0, h=4, text=escape(comparison_content))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path

