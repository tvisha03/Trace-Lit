
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import Cell

from shared.logger import get_logger
from shared.utils.export_text import strip_markdown

logger = get_logger(__name__)

_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="4A6FA5", end_color="4A6FA5", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")


def _set_cell_value_and_wrap(ws: Worksheet, row: int, col: int, value: str) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.alignment = _WRAP_ALIGNMENT


def _set_column_widths(ws: Worksheet) -> None:
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
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _WRAP_ALIGNMENT


def _populate_comparison_rows(ws: Worksheet, paper_data: list[dict]) -> None:
    for row_idx, paper in enumerate(paper_data, start=2):
        _set_cell_value_and_wrap(ws, row_idx, 1, str(paper.get("title", "")))
        _set_cell_value_and_wrap(ws, row_idx, 2, str(paper.get("authors", "")))
        ws.cell(row=row_idx, column=3, value=paper.get("year", ""))
        _set_cell_value_and_wrap(ws, row_idx, 4, str(paper.get("problem", "")))
        _set_cell_value_and_wrap(ws, row_idx, 5, str(paper.get("method", "")))
        _set_cell_value_and_wrap(ws, row_idx, 6, str(paper.get("results", "")))
        _set_cell_value_and_wrap(ws, row_idx, 7, str(paper.get("keywords", "")))


def _populate_citation_rows(ws: Worksheet, citations: list[dict]) -> None:
    for row_idx, cit in enumerate(citations, start=2):
        _set_cell_value_and_wrap(ws, row_idx, 1, strip_markdown(str(cit.get("claim", ""))))
        ws.cell(row=row_idx, column=2, value=cit.get("confidence", ""))
        ws.cell(row=row_idx, column=3, value=cit.get("score", 0.0))
        _set_cell_value_and_wrap(ws, row_idx, 4, strip_markdown(str(cit.get("source_sentence", ""))))
        ws.cell(row=row_idx, column=5, value=cit.get("paragraph_id", ""))

def export_comparison_to_excel(
    paper_data: list[dict],
    output_path: str | Path,
    comparison_content: str = "",
) -> Path:
    output_path = Path(output_path)
    wb = Workbook()

    # --- Sheet 1: Comparison Analysis ---
    ws_comp = wb.active
    if ws_comp is None:
        raise ValueError("Failed to create worksheet")
    ws_comp.title = "Comparison"

    ws_comp.cell(row=1, column=1, value="Paper Comparison Analysis").font = Font(bold=True, size=13)
    ws_comp.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)

    cleaned = strip_markdown(comparison_content) if comparison_content else ""
    if cleaned:
        for row_idx, paragraph in enumerate(cleaned.split("\n"), start=3):
            paragraph = paragraph.strip()
            if paragraph:
                _set_cell_value_and_wrap(ws_comp, row_idx, 1, paragraph)
    _set_column_widths(ws_comp)
    # Ensure the comparison column is wide enough to read
    ws_comp.column_dimensions["A"].width = 100

    # --- Sheet 2: Paper Details ---
    ws_papers = wb.create_sheet(title="Paper Details")
    headers = ["Title", "Authors", "Year", "Problem", "Method", "Results", "Keywords"]
    _set_header_row(ws_papers, headers)
    _populate_comparison_rows(ws_papers, paper_data)
    _set_column_widths(ws_papers)

    wb.save(str(output_path))
    logger.info(f"Exported comparison Excel to {output_path.name}")
    return output_path

def export_citations_to_excel(
    citations: list[dict],
    output_path: str | Path,
    session_title: str = "Chat Export",
    messages: list[dict] | None = None,
) -> Path:
    """Export chat data to Excel with two sheets: Chat History and Citation Verification."""
    output_path = Path(output_path)
    wb = Workbook()

    # --- Sheet 1: Chat History ---
    ws_chat = wb.active
    if ws_chat is None:
        raise ValueError("Failed to create worksheet")
    ws_chat.title = session_title[:31]  # Excel sheet names max 31 chars

    chat_headers = ["Role", "Content"]
    _set_header_row(ws_chat, chat_headers)

    if messages:
        for row_idx, msg in enumerate(messages, start=2):
            role = msg.get("role", "user").upper()
            content = strip_markdown(msg.get("content", ""))
            _set_cell_value_and_wrap(ws_chat, row_idx, 1, role)
            _set_cell_value_and_wrap(ws_chat, row_idx, 2, content)
    _set_column_widths(ws_chat)

    # --- Sheet 2: Citation Verification ---
    ws_cit = wb.create_sheet(title="Citation Verification")
    cit_headers = ["Claim", "Confidence", "Score", "Source Sentence", "Paragraph ID"]
    _set_header_row(ws_cit, cit_headers)
    _populate_citation_rows(ws_cit, citations)
    _set_column_widths(ws_cit)

    wb.save(str(output_path))
    logger.info(f"Exported citations Excel to {output_path.name}")
    return output_path

