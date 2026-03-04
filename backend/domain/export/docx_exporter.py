
from pathlib import Path

from shared.logger import get_logger
from shared.errors import TraceLitError
from shared.utils.export_text import strip_markdown

logger = get_logger(__name__)


def _confidence_rgb(confidence: str):
    from docx.shared import RGBColor

    if confidence == "high":
        return RGBColor(52, 211, 153)
    if confidence == "medium":
        return RGBColor(251, 191, 36)
    return RGBColor(248, 113, 113)


def _add_message_to_doc(doc, msg, Pt, RGBColor, WD_ALIGN_PARAGRAPH):
    """Add a single message (role, content, verification) to document."""
    role = msg.get("role", "user").upper()
    content = msg.get("content", "")
    havf_results = msg.get("havf_results") or []

    role_para = doc.add_paragraph()
    role_run = role_para.add_run(f"[{role}]")
    role_run.bold = True
    role_run.font.size = Pt(11)
    if role == "ASSISTANT":
        role_run.font.color.rgb = RGBColor(0, 0, 139)

    content_para = doc.add_paragraph(strip_markdown(content))
    content_para.style.font.size = Pt(10)

    if havf_results:
        _add_verification_section(doc, havf_results, Pt, RGBColor)


def _add_verification_section(doc, havf_results, Pt, RGBColor):
    """Add verification results section for a message."""
    verif_para = doc.add_paragraph()
    verif_run = verif_para.add_run("Verification:")
    verif_run.italic = True
    verif_run.font.size = Pt(9)
    verif_run.font.color.rgb = RGBColor(100, 100, 100)

    for r in havf_results:
        confidence = r.get("confidence", "low")
        claim = r.get("claim", "")[:200]
        paragraph_id = r.get("paragraph_id", "")
        score = r.get("score", 0)

        line = f"  {confidence.upper()} ({score:.2f})"
        if paragraph_id:
            line += f" [{paragraph_id}]"
        line += f' — "{claim}"'

        r_para = doc.add_paragraph()
        r_run = r_para.add_run(line)
        r_run.font.size = Pt(8)
        r_run.font.color.rgb = _confidence_rgb(confidence)


def export_chat_to_docx(
    session_title: str,
    messages: list[dict],
    output_path: str | Path,
) -> Path:
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError as exc:
        raise TraceLitError(
            message="python-docx library not installed — Word export unavailable.",
            status_code=501,
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    title_para = doc.add_heading(session_title, level=1)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for msg in messages:
        _add_message_to_doc(doc, msg, Pt, RGBColor, WD_ALIGN_PARAGRAPH)

    try:
        doc.save(str(output_path))
    except Exception as exc:
        raise TraceLitError(
            message=f"Failed to generate Word document: {exc}",
            status_code=500,
        ) from exc

    logger.info(f"Exported chat DOCX to {output_path.name}")
    return output_path


def export_comparison_to_docx(
    title: str,
    comparison_content: str,
    paper_titles: list[str],
    output_path: str | Path,
) -> Path:
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError as exc:
        raise TraceLitError(
            message="python-docx library not installed — Word export unavailable.",
            status_code=501,
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    heading = doc.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading("Papers Compared", level=2)
    for pt in paper_titles:
        doc.add_paragraph(pt, style="List Bullet")

    doc.add_heading("Comparison", level=2)
    doc.add_paragraph(strip_markdown(comparison_content))

    try:
        doc.save(str(output_path))
    except Exception as exc:
        raise TraceLitError(
            message=f"Failed to generate comparison DOCX: {exc}",
            status_code=500,
        ) from exc

    logger.info(f"Exported comparison DOCX to {output_path.name}")
    return output_path

