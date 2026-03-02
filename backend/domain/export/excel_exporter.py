
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import Cell

from shared.logger import get_logger

logger = get_logger(__name__)

_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="4A6FA5", end_color="4A6FA5", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")


def _set_cell_value_and_wrap(ws: Worksheet, row: int, col: int, value: str) -> None:
    """Set cell value with text wrapping."""
    cell = ws.cell(row=row, column=col, value=value)
    cell.alignment = _WRAP_ALIGNMENT


def _set_column_widths(ws: Worksheet) -> None:
    """Auto-fit column widths based on content."""
    for col in ws.columns:
        if not col or col[0] is None:
            continue
        first_cell = col[0]
        if not isinstance(first_cell, Cell):
            continue
        max_len = max(
            (len(str(cell.value or "")) for cell in col if cell is not None),
            default=10
        )
        ws.column_dimensions[first_cell.column_letter].width = min(max_len + 2, 60)


def _set_header_row(ws: Worksheet, headers: list[str]) -> None:
    """Format header row."""
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _WRAP_ALIGNMENT


def _populate_comparison_rows(ws: Worksheet, paper_data: list[dict]) -> None:
    """Populate comparison data rows."""
    for row_idx, paper in enumerate(paper_data, start=2):
        _set_cell_value_and_wrap(ws, row_idx, 1, str(paper.get("title", "")))
        _set_cell_value_and_wrap(ws, row_idx, 2, str(paper.get("authors", "")))
        ws.cell(row=row_idx, column=3, value=paper.get("year", ""))
        _set_cell_value_and_wrap(ws, row_idx, 4, str(paper.get("problem", "")))
        _set_cell_value_and_wrap(ws, row_idx, 5, str(paper.get("method", "")))
        _set_cell_value_and_wrap(ws, row_idx, 6, str(paper.get("results", "")))
        _set_cell_value_and_wrap(ws, row_idx, 7, str(paper.get("keywords", "")))


def _populate_citation_rows(ws: Worksheet, citations: list[dict]) -> None:
    """Populate citation data rows."""
    for row_idx, cit in enumerate(citations, start=2):
        _set_cell_value_and_wrap(ws, row_idx, 1, str(cit.get("claim", "")))
        ws.cell(row=row_idx, column=2, value=cit.get("confidence", ""))
        ws.cell(row=row_idx, column=3, value=cit.get("score", 0.0))
        _set_cell_value_and_wrap(ws, row_idx, 4, str(cit.get("source_sentence", "")))
        ws.cell(row=row_idx, column=5, value=cit.get("paragraph_id", ""))

def export_comparison_to_excel(
    paper_data: list[dict],
    output_path: str | Path,
) -> Path:
    """Export paper comparison data to Excel file."""
    output_path = Path(output_path)
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise ValueError("Failed to create worksheet")

    ws.title = "Paper Comparison"
    headers = ["Title", "Authors", "Year", "Problem", "Method", "Results", "Keywords"]
    _set_header_row(ws, headers)
    _populate_comparison_rows(ws, paper_data)
    _set_column_widths(ws)

    wb.save(str(output_path))
    logger.info(f"Exported comparison Excel to {output_path.name}")
    return output_path

def export_citations_to_excel(
    citations: list[dict],
    output_path: str | Path,
) -> Path:
    """Export citation verification data to Excel file."""
    output_path = Path(output_path)
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise ValueError("Failed to create worksheet")

    ws.title = "Citation Verification"
    headers = ["Claim", "Confidence", "Score", "Source Sentence", "Paragraph ID"]
    _set_header_row(ws, headers)
    _populate_citation_rows(ws, citations)
    _set_column_widths(ws)

    wb.save(str(output_path))
    logger.info(f"Exported citations Excel to {output_path.name}")
    return output_path
