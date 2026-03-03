
from pathlib import Path
from html import escape
from jinja2 import Environment, FileSystemLoader

from shared.logger import get_logger
from shared.errors import PDFExportError
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )

def _truncate_text(text: str, max_chars: int = 10000) -> str:
    """Soft-truncate extremely long text as a safety net (10 000 chars default).

    The previous 800/2000 char limits were far too aggressive for academic
    content.  Now we allow virtually unlimited length for normal messages
    and only truncate truly enormous content (BUG-8 fix).
    """
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text

def _havf_confidence_color(confidence: str) -> tuple[int, int, int]:
    """Return an RGB colour tuple for a HAVF confidence level."""
    if confidence == "high":
        return (86, 184, 112)   # green
    if confidence == "medium":
        return (244, 162, 97)   # amber
    return (231, 111, 81)       # red

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
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                havf_results = msg.get("havf_results") or []

                pdf.set_font("Helvetica", "B", 10)
                if role == "ASSISTANT":
                    pdf.set_text_color(0, 0, 139)
                else:
                    pdf.set_text_color(60, 60, 60)
                pdf.cell(w=0, h=5, text=f"[{role}]", ln=True)
                pdf.set_text_color(0, 0, 0)

                # BUG-8 fix: No aggressive truncation — render full content.
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(w=0, h=4, text=escape(content))

                # BUG-6 fix: Render HAVF verification results when present.
                if havf_results:
                    pdf.ln(1)
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(w=0, h=4, text="Verification:", ln=True)
                    for r in havf_results:
                        confidence = r.get("confidence", "low")
                        claim = r.get("claim", "")[:120]
                        paragraph_id = r.get("paragraph_id", "")
                        score = r.get("score", 0)

                        cr, cg, cb = _havf_confidence_color(confidence)
                        pdf.set_text_color(cr, cg, cb)
                        pdf.set_font("Helvetica", "B", 8)
                        line = f"  {confidence.upper()} ({score:.2f})"
                        if paragraph_id:
                            line += f" [{paragraph_id}]"
                        line += f" — \"{claim}\""
                        pdf.multi_cell(w=0, h=3.5, text=line)

                    pdf.set_text_color(0, 0, 0)

                pdf.ln(2)

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

        # BUG-8 fix: No aggressive truncation — render full comparison.
        pdf.multi_cell(w=0, h=4, text=escape(comparison_content))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path
