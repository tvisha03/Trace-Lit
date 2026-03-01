"""
PDF Exporter — renders chat sessions and comparisons to PDF using fpdf2 (pure Python, no system dependencies).
"""

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


def _truncate_text(text: str, max_chars: int = 500) -> str:
    """Truncate text safely for PDF display."""
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def export_chat_to_pdf(
    session_title: str,
    messages: list[dict],
    output_path: str | Path,
) -> Path:
    """
    Render a chat session to a styled PDF.

    Args:
        session_title: title shown at the top of the export.
        messages: list of dicts with ``role``, ``content``, optional ``havf_results``.
        output_path: filesystem path for the output PDF.

    Returns:
        Path to the written PDF file.
    """
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

            # Title
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(w=0, h=10, text=_truncate_text(session_title, 100), ln=True, align="C")
            pdf.ln(3)

            # Messages
            for msg in messages:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")

                # Role header
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(0, 0, 139) if role == "ASSISTANT" else pdf.set_text_color(60, 60, 60)
                pdf.cell(w=0, h=5, text=f"[{role}]", ln=True)
                pdf.set_text_color(0, 0, 0)

                # Content
                pdf.set_font("Helvetica", "", 9)
                truncated = _truncate_text(content, 800)
                # Use multi_cell with proper width (0 = full width between margins)
                pdf.multi_cell(w=0, h=4, text=escape(truncated))
                pdf.ln(2)

            # Create directory if it doesn't exist
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
    """Render a paper comparison to a styled PDF."""
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise PDFExportError("fpdf2 library not installed") from e

    output_path = Path(output_path)

    try:
        pdf = FPDF(format="A4", unit="mm")
        pdf.set_margins(left=15, top=15, right=15)
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(w=0, h=10, text=_truncate_text(title, 100), ln=True, align="C")

        # Papers section
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(w=0, h=6, text="Papers Compared:", ln=True)
        pdf.set_font("Helvetica", "", 9)

        for paper in paper_titles:
            truncated_paper = _truncate_text(paper, 80)
            pdf.cell(w=5, h=4, text="•")
            pdf.multi_cell(w=0, h=4, text=escape(truncated_paper))

        # Comparison section
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(w=0, h=6, text="Comparison:", ln=True)
        pdf.set_font("Helvetica", "", 9)

        truncated_content = _truncate_text(comparison_content, 2000)
        pdf.multi_cell(w=0, h=4, text=escape(truncated_content))

        # Create directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
    except Exception as e:
        raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path
