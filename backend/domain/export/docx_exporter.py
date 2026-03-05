
from datetime import datetime
from pathlib import Path

from shared.logger import get_logger
from shared.errors import TraceLitError
from shared.utils.export_text import strip_markdown, format_structured_text

logger = get_logger(__name__)

def _confidence_rgb(confidence: str):
    from docx.shared import RGBColor

    if confidence == "high":
        return RGBColor(34, 139, 34)
    if confidence == "medium":
        return RGBColor(204, 153, 0)
    return RGBColor(204, 51, 51)

def _add_separator(doc, Pt, RGBColor) -> None:
    from docx.oxml.ns import qn

    sep = doc.add_paragraph()
    sep.paragraph_format.space_before = Pt(2)
    sep.paragraph_format.space_after = Pt(2)
    pPr = sep._element.get_or_add_pPr()
    pBdr = pPr.makeelement(qn("w:pBdr"), {})
    bottom = pBdr.makeelement(qn("w:bottom"), {
        qn("w:val"): "single",
        qn("w:sz"): "4",
        qn("w:space"): "1",
        qn("w:color"): "D0D0D0",
    })
    pBdr.append(bottom)
    pPr.append(pBdr)

def _add_message_to_doc(doc, msg, Pt, RGBColor, WD_ALIGN_PARAGRAPH):
    role = msg.get("role", "user").upper()
    content = msg.get("content", "")
    havf_results = msg.get("havf_results") or []

    role_para = doc.add_paragraph()
    role_para.paragraph_format.space_before = Pt(6)
    role_para.paragraph_format.space_after = Pt(2)
    role_run = role_para.add_run(f"[{role}]")
    role_run.bold = True
    role_run.font.size = Pt(11)
    if role == "ASSISTANT":
        role_run.font.color.rgb = RGBColor(0, 51, 153)

    cleaned = strip_markdown(content)
    for paragraph_text in cleaned.split("\n\n"):
        paragraph_text = paragraph_text.strip()
        if not paragraph_text:
            continue
        content_para = doc.add_paragraph(paragraph_text)
        content_para.paragraph_format.space_after = Pt(4)
        for run in content_para.runs:
            run.font.size = Pt(10)

    if havf_results:
        _add_verification_section(doc, havf_results, Pt, RGBColor)

    _add_separator(doc, Pt, RGBColor)

def _add_verification_section(doc, havf_results, Pt, RGBColor):
    verif_para = doc.add_paragraph()
    verif_para.paragraph_format.space_before = Pt(4)
    verif_run = verif_para.add_run("Citation Verification:")
    verif_run.italic = True
    verif_run.font.size = Pt(9)
    verif_run.font.color.rgb = RGBColor(100, 100, 100)

    for r in havf_results:
        confidence = r.get("confidence", "low")
        raw_claim = r.get("claim", "")
        claim = raw_claim[:500].rsplit(" ", 1)[0] + "..." if len(raw_claim) > 500 else raw_claim
        paragraph_id = r.get("paragraph_id", "")
        chunk_type = r.get("chunk_type", "")
        score = r.get("score", 0)

        r_para = doc.add_paragraph()
        r_para.paragraph_format.space_before = Pt(1)
        r_para.paragraph_format.space_after = Pt(1)

        badge_run = r_para.add_run(f"  [{confidence.upper()}] ({score:.0%})")
        badge_run.bold = True
        badge_run.font.size = Pt(8)
        badge_run.font.color.rgb = _confidence_rgb(confidence)

        if paragraph_id:
            ref_run = r_para.add_run(f"  [{paragraph_id}]")
            ref_run.font.size = Pt(8)
            ref_run.font.color.rgb = RGBColor(100, 100, 100)

        if chunk_type and chunk_type != "text":
            type_run = r_para.add_run(f"  ({chunk_type})")
            type_run.font.size = Pt(8)
            type_run.font.color.rgb = RGBColor(100, 100, 100)

        claim_run = r_para.add_run(f'  "{claim}"')
        claim_run.font.size = Pt(8)
        claim_run.font.color.rgb = RGBColor(80, 80, 80)

def _setup_doc_with_heading_and_date(doc, title, Pt, RGBColor, WD_ALIGN_PARAGRAPH):
    heading = doc.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_para.paragraph_format.space_after = Pt(12)
    date_run = date_para.add_run(f"Exported on {datetime.now().strftime('%B %d, %Y')}")
    date_run.font.size = Pt(9)
    date_run.font.color.rgb = RGBColor(120, 120, 120)

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

    _setup_doc_with_heading_and_date(doc, session_title, Pt, RGBColor, WD_ALIGN_PARAGRAPH)

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

    _setup_doc_with_heading_and_date(doc, title, Pt, RGBColor, WD_ALIGN_PARAGRAPH)

    doc.add_heading("Papers Compared", level=2)
    for pt in paper_titles:
        p = doc.add_paragraph(style="List Number")
        run = p.add_run(pt)
        run.font.size = Pt(10)

    doc.add_heading("Comparison Analysis", level=2)
    cleaned = format_structured_text(comparison_content)
    for paragraph_text in cleaned.split("\n\n"):
        paragraph_text = paragraph_text.strip()
        if not paragraph_text:
            continue
        p = doc.add_paragraph(paragraph_text)
        p.paragraph_format.space_after = Pt(6)
        for run in p.runs:
            run.font.size = Pt(10)

    try:
        doc.save(str(output_path))
    except Exception as exc:
        raise TraceLitError(
            message=f"Failed to generate comparison DOCX: {exc}",
            status_code=500,
        ) from exc

    logger.info(f"Exported comparison DOCX to {output_path.name}")
    return output_path

