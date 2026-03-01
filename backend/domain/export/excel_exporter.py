"""
Excel Exporter — exports structured data (comparisons, keywords, citations) to .xlsx.
Uses openpyxl for workbook creation.
"""

from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from shared.logger import get_logger

logger = get_logger(__name__)

# Styling constants
_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="4A6FA5", end_color="4A6FA5", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")


def export_comparison_to_excel(
    paper_data: list[dict],
    output_path: str | Path,
) -> Path:
    """
    Export a structured paper comparison to an Excel workbook.

    Args:
        paper_data: list of dicts, each with keys like ``title``, ``authors``,
                    ``year``, ``problem``, ``method``, ``results``, ``keywords``.
        output_path: filesystem path for the .xlsx file.
    """
    output_path = Path(output_path)
    wb = Workbook()
    ws = wb.active  # type: ignore
    ws.title = "Paper Comparison"  # type: ignore

    # Header row
    headers = ["Title", "Authors", "Year", "Problem", "Method", "Results", "Keywords"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)  # type: ignore
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _WRAP_ALIGNMENT

    # Data rows
    for row_idx, paper in enumerate(paper_data, start=2):
        ws.cell(row=row_idx, column=1, value=paper.get("title", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=2, value=paper.get("authors", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=3, value=paper.get("year", ""))  # type: ignore
        ws.cell(row=row_idx, column=4, value=paper.get("problem", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=5, value=paper.get("method", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=6, value=paper.get("results", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=7, value=paper.get("keywords", "")).alignment = _WRAP_ALIGNMENT  # type: ignore

    # Auto-width (approximate)
    for col in ws.columns:  # type: ignore
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        if col and hasattr(col[0], 'column_letter'):
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)  # type: ignore

    wb.save(str(output_path))
    logger.info(f"Exported comparison Excel to {output_path.name}")
    return output_path


def export_citations_to_excel(
    citations: list[dict],
    output_path: str | Path,
) -> Path:
    """
    Export HAVF verification results to an Excel sheet.

    Args:
        citations: list of dicts with ``claim``, ``confidence``, ``score``,
                   ``source_sentence``, ``paragraph_id``.
    """
    output_path = Path(output_path)
    wb = Workbook()
    ws = wb.active  # type: ignore
    ws.title = "Citation Verification"  # type: ignore

    headers = ["Claim", "Confidence", "Score", "Source Sentence", "Paragraph ID"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)  # type: ignore
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    for row_idx, cit in enumerate(citations, start=2):
        ws.cell(row=row_idx, column=1, value=cit.get("claim", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=2, value=cit.get("confidence", ""))  # type: ignore
        ws.cell(row=row_idx, column=3, value=cit.get("score", 0.0))  # type: ignore
        ws.cell(row=row_idx, column=4, value=cit.get("source_sentence", "")).alignment = _WRAP_ALIGNMENT  # type: ignore
        ws.cell(row=row_idx, column=5, value=cit.get("paragraph_id", ""))  # type: ignore

    for col in ws.columns:  # type: ignore
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        if col and hasattr(col[0], 'column_letter'):
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)  # type: ignore

    wb.save(str(output_path))
    logger.info(f"Exported citations Excel to {output_path.name}")
    return output_path
