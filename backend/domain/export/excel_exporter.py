"""TraceLit — Excel Export via openpyxl.

Exports comparison tables and session metadata to Excel workbooks.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


def generate_comparison_excel(
    comparison_data: Dict[str, Any],
    output_dir: str = None,
) -> str:
    """Export comparison table to Excel.

    Args:
        comparison_data: Dict with keys:
            - session_id, session_name
            - papers: list of paper metadata
            - rows: comparison rows from comparison engine
            - contributions: per-paper contribution dicts

    Returns:
        Path to generated Excel file.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    except ImportError:
        logger.error("openpyxl not installed — Excel export unavailable")
        raise RuntimeError("openpyxl is required for Excel export")

    if output_dir is None:
        from app.config import settings
        output_dir = settings.export_dir

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    session_id = comparison_data.get("session_id", "unknown")
    papers = comparison_data.get("papers", [])
    rows = comparison_data.get("rows", [])

    wb = Workbook()

    # ─── Sheet 1: Comparison Table ───
    ws = wb.active
    ws.title = "Comparison"

    # Styles
    header_font = Font(bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    field_font = Font(bold=True, size=11)
    field_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    wrap_alignment = Alignment(wrap_text=True, vertical="top")

    # Header row: Field | Paper 1 | Paper 2 | ...
    ws.cell(row=1, column=1, value="Aspect").font = header_font
    ws.cell(row=1, column=1).fill = header_fill
    ws.cell(row=1, column=1).border = border

    for col_idx, paper in enumerate(papers, start=2):
        title = paper.get("title", "Unknown")
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        ws.column_dimensions[chr(64 + col_idx)].width = 35

    ws.column_dimensions["A"].width = 15

    # Data rows
    field_labels = {
        "problem": "Problem",
        "method": "Method",
        "dataset": "Dataset",
        "metrics": "Metrics",
        "results": "Results",
    }

    for row_idx, row_data in enumerate(rows, start=2):
        field = row_data.get("field", "")
        label = field_labels.get(field, field.capitalize())

        cell = ws.cell(row=row_idx, column=1, value=label)
        cell.font = field_font
        cell.fill = field_fill
        cell.border = border

        paper_values = row_data.get("papers", {})
        for col_idx, paper in enumerate(papers, start=2):
            pid = paper.get("id", paper.get("paper_id", ""))
            entry = paper_values.get(pid, {})
            value = entry.get("value", "Not specified")
            source = entry.get("source", "")

            cell_value = value
            if source:
                cell_value += f"\n[Source: {source}]"

            cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
            cell.alignment = wrap_alignment
            cell.border = border

    # ─── Sheet 2: Paper Metadata ───
    ws2 = wb.create_sheet(title="Papers")
    meta_headers = ["Title", "Authors", "Year", "Pages", "Status"]
    for col_idx, header in enumerate(meta_headers, start=1):
        cell = ws2.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    for row_idx, paper in enumerate(papers, start=2):
        authors = paper.get("authors", [])
        if isinstance(authors, str):
            import json
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors]

        ws2.cell(row=row_idx, column=1, value=paper.get("title", "Unknown")).border = border
        ws2.cell(row=row_idx, column=2, value=", ".join(authors)).border = border
        ws2.cell(row=row_idx, column=3, value=paper.get("year", "")).border = border
        ws2.cell(row=row_idx, column=4, value=paper.get("pages", "")).border = border
        ws2.cell(row=row_idx, column=5, value=paper.get("status", "")).border = border

    for col in ["A", "B", "C", "D", "E"]:
        ws2.column_dimensions[col].width = 25

    # ─── Sheet 3: Export Info ───
    ws3 = wb.create_sheet(title="Info")
    ws3.cell(row=1, column=1, value="Export Date").font = Font(bold=True)
    ws3.cell(row=1, column=2, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ws3.cell(row=2, column=1, value="Session ID").font = Font(bold=True)
    ws3.cell(row=2, column=2, value=session_id)
    ws3.cell(row=3, column=1, value="Papers Count").font = Font(bold=True)
    ws3.cell(row=3, column=2, value=len(papers))
    ws3.cell(row=4, column=1, value="Generated By").font = Font(bold=True)
    ws3.cell(row=4, column=2, value="TraceLit — AI Research Paper Analysis")
    ws3.column_dimensions["A"].width = 20
    ws3.column_dimensions["B"].width = 40

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tracelit_comparison_{session_id[:8]}_{timestamp}.xlsx"
    output_path = os.path.join(output_dir, filename)

    wb.save(output_path)
    logger.info("Excel generated: {} ({} papers)", output_path, len(papers))
    return output_path


def generate_session_excel(
    session_data: Dict[str, Any],
    output_dir: str = None,
) -> str:
    """Export full session data to Excel.

    Args:
        session_data: Dict with session_id, session_name, messages, papers.

    Returns:
        Path to generated Excel file.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    except ImportError:
        raise RuntimeError("openpyxl is required for Excel export")

    if output_dir is None:
        from app.config import settings
        output_dir = settings.export_dir

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    session_id = session_data.get("session_id", "unknown")
    messages = session_data.get("messages", [])
    papers = session_data.get("papers", [])

    wb = Workbook()

    # Styles
    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    wrap = Alignment(wrap_text=True, vertical="top")

    # ─── Sheet 1: Messages ───
    ws = wb.active
    ws.title = "Conversation"

    msg_headers = ["#", "Role", "Content", "Confidence", "Provider"]
    for col_idx, h in enumerate(msg_headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    for row_idx, msg in enumerate(messages, 2):
        metadata = msg.get("metadata", {}) or {}
        ws.cell(row=row_idx, column=1, value=row_idx - 1).border = border
        ws.cell(row=row_idx, column=2, value=msg.get("role", "")).border = border
        cell = ws.cell(row=row_idx, column=3, value=msg.get("content", ""))
        cell.border = border
        cell.alignment = wrap
        ws.cell(row=row_idx, column=4, value=metadata.get("overall_confidence", "")).border = border
        ws.cell(row=row_idx, column=5, value=metadata.get("provider", "")).border = border

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 80
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 12

    # ─── Sheet 2: Papers ───
    ws2 = wb.create_sheet(title="Papers")
    paper_headers = ["Title", "Authors", "Year", "Pages"]
    for col_idx, h in enumerate(paper_headers, 1):
        cell = ws2.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    for row_idx, paper in enumerate(papers, 2):
        authors = paper.get("authors", [])
        if isinstance(authors, str):
            import json
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors]
        ws2.cell(row=row_idx, column=1, value=paper.get("title", "")).border = border
        ws2.cell(row=row_idx, column=2, value=", ".join(authors)).border = border
        ws2.cell(row=row_idx, column=3, value=paper.get("year", "")).border = border
        ws2.cell(row=row_idx, column=4, value=paper.get("pages", "")).border = border

    for col in ["A", "B", "C", "D"]:
        ws2.column_dimensions[col].width = 30

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tracelit_session_{session_id[:8]}_{timestamp}.xlsx"
    output_path = os.path.join(output_dir, filename)

    wb.save(output_path)
    logger.info("Session Excel generated: {}", output_path)
    return output_path
