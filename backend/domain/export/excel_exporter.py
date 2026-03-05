
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter

from shared.logger import get_logger
from shared.utils.export_text import strip_markdown, format_structured_text

logger = get_logger(__name__)

_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="2F4F6F", end_color="2F4F6F", fill_type="solid")
_EVEN_ROW_FILL = PatternFill(start_color="F5F7FA", end_color="F5F7FA", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")
_THIN_BORDER = Border(
    left=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
    top=Side(style="thin", color="D0D0D0"),
    bottom=Side(style="thin", color="D0D0D0"),
)

_CONF_FILLS = {
    "high": PatternFill(start_color="E6F5EC", end_color="E6F5EC", fill_type="solid"),
    "medium": PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid"),
    "low": PatternFill(start_color="FDECEA", end_color="FDECEA", fill_type="solid"),
}
_CONF_FONTS = {
    "high": Font(bold=True, color="1B7A3D"),
    "medium": Font(bold=True, color="B8860B"),
    "low": Font(bold=True, color="CC3333"),
}

def _set_cell(ws: Worksheet, row: int, col: int, value: str,
              font: Font | None = None, fill: PatternFill | None = None) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.alignment = _WRAP_ALIGNMENT
    cell.border = _THIN_BORDER
    if font:
        cell.font = font
    if fill:
        cell.fill = fill

def _auto_column_widths(ws: Worksheet, min_width: int = 12, max_width: int = 65) -> None:
    for col_cells in ws.columns:
        if not col_cells or col_cells[0] is None:
            continue
        first = col_cells[0]
        if not isinstance(first, Cell):
            continue
        longest = max(
            (len(str(c.value or "")) for c in col_cells if c is not None),
            default=min_width,
        )
        ws.column_dimensions[first.column_letter].width = max(
            min_width, min(longest + 3, max_width)
        )

def _set_header_row(ws: Worksheet, headers: list[str]) -> None:
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _WRAP_ALIGNMENT
        cell.border = _THIN_BORDER
    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last_col}1"

def _apply_alternating_rows(ws: Worksheet, start_row: int = 2) -> None:
    for row in ws.iter_rows(min_row=start_row, max_row=ws.max_row):
        if row[0].row % 2 == 0:
            for cell in row:
                if cell.fill == PatternFill():
                    cell.fill = _EVEN_ROW_FILL

def _populate_comparison_rows(ws: Worksheet, paper_data: list[dict]) -> None:
    for row_idx, paper in enumerate(paper_data, start=2):
        _set_cell(ws, row_idx, 1, str(paper.get("title", "")))
        _set_cell(ws, row_idx, 2, str(paper.get("authors", "")))
        ws.cell(row=row_idx, column=3, value=paper.get("year", "")).border = _THIN_BORDER
        _set_cell(ws, row_idx, 4, str(paper.get("abstract", "") or ""))
        _set_cell(ws, row_idx, 5, str(paper.get("problem", "") or ""))
        _set_cell(ws, row_idx, 6, str(paper.get("method", "") or ""))
        _set_cell(ws, row_idx, 7, str(paper.get("results", "") or ""))
        _set_cell(ws, row_idx, 8, str(paper.get("keywords", "") or ""))

def _populate_citation_rows(ws: Worksheet, citations: list[dict]) -> None:
    for row_idx, cit in enumerate(citations, start=2):
        _set_cell(ws, row_idx, 1, strip_markdown(str(cit.get("claim", ""))))

        confidence = str(cit.get("confidence", "low")).lower()
        conf_cell = ws.cell(row=row_idx, column=2, value=confidence.upper())
        conf_cell.font = _CONF_FONTS.get(confidence, _CONF_FONTS["low"])
        conf_cell.fill = _CONF_FILLS.get(confidence, _CONF_FILLS["low"])
        conf_cell.alignment = _WRAP_ALIGNMENT
        conf_cell.border = _THIN_BORDER

        score = cit.get("score", 0.0)
        score_cell = ws.cell(row=row_idx, column=3, value=score)
        score_cell.number_format = "0%"
        score_cell.border = _THIN_BORDER

        _set_cell(ws, row_idx, 4, strip_markdown(str(cit.get("source_sentence", ""))))
        _set_cell(ws, row_idx, 5, str(cit.get("paragraph_id", "")))

def export_comparison_to_excel(
    paper_data: list[dict],
    output_path: str | Path,
    comparison_content: str = "",
) -> Path:
    output_path = Path(output_path)
    wb = Workbook()

    ws_comp = wb.active
    if ws_comp is None:
        raise ValueError("Failed to create worksheet")
    ws_comp.title = "Comparison"

    title_cell = ws_comp.cell(row=1, column=1, value="Paper Comparison Analysis")
    title_cell.font = Font(bold=True, size=14, color="2F4F6F")
    ws_comp.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)

    date_cell = ws_comp.cell(
        row=2, column=1,
        value=f"Exported on {datetime.now().strftime('%B %d, %Y')}",
    )
    date_cell.font = Font(italic=True, size=9, color="888888")

    cleaned = format_structured_text(comparison_content) if comparison_content else ""
    if cleaned:
        row_idx = 4
        for paragraph in cleaned.split("\n\n"):
            paragraph = paragraph.strip()
            if paragraph:
                _set_cell(ws_comp, row_idx, 1, paragraph)
                row_idx += 1
    _auto_column_widths(ws_comp)
    ws_comp.column_dimensions["A"].width = 110

    ws_papers = wb.create_sheet(title="Paper Details")
    headers = ["Title", "Authors", "Year", "Abstract", "Problem", "Method", "Results", "Keywords"]
    _set_header_row(ws_papers, headers)
    _populate_comparison_rows(ws_papers, paper_data)
    _apply_alternating_rows(ws_papers)
    _auto_column_widths(ws_papers)

    wb.save(str(output_path))
    logger.info(f"Exported comparison Excel to {output_path.name}")
    return output_path

def export_citations_to_excel(
    citations: list[dict],
    output_path: str | Path,
    session_title: str = "Chat Export",
    messages: list[dict] | None = None,
) -> Path:
    output_path = Path(output_path)
    wb = Workbook()

    ws_chat = wb.active
    if ws_chat is None:
        raise ValueError("Failed to create worksheet")
    ws_chat.title = session_title[:31]

    chat_headers = ["Role", "Content"]
    _set_header_row(ws_chat, chat_headers)

    if messages:
        for row_idx, msg in enumerate(messages, start=2):
            role = msg.get("role", "user").upper()
            content = strip_markdown(msg.get("content", ""))
            _set_cell(ws_chat, row_idx, 1, role)
            _set_cell(ws_chat, row_idx, 2, content)
    _apply_alternating_rows(ws_chat)
    _auto_column_widths(ws_chat)

    ws_cit = wb.create_sheet(title="Citation Verification")
    cit_headers = ["Claim", "Confidence", "Score", "Source Sentence", "Paragraph ID"]
    _set_header_row(ws_cit, cit_headers)
    _populate_citation_rows(ws_cit, citations)
    _apply_alternating_rows(ws_cit)
    _auto_column_widths(ws_cit)

    wb.save(str(output_path))
    logger.info(f"Exported citations Excel to {output_path.name}")
    return output_path

