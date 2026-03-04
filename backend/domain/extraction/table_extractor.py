"""TraceLit — Table Extractor.

Extracts tables from academic PDFs using two complementary strategies:

  1. **Structural** — PyMuPDF ``page.find_tables()`` detects tables rendered
     with ruled lines or cell borders.  Works on any PDF that has explicit
     table structure.

  2. **Markdown-pipe** — pymupdf4llm often renders tables as Markdown pipe-
     tables (``| col | col |``).  We detect and normalise those.

  3. **Text-heuristic** — For papers where tables are typeset as aligned
     whitespace columns (common in arXiv PDFs), we detect contiguous runs
     of numeric-dense lines and convert them to Markdown.

All strategies are generic — they work on any academic PDF, not just a
specific paper.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from loguru import logger


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractedTable:
    """A single table extracted from a PDF page."""
    page_number: int          # 1-based
    table_index: int          # 0-based index on page
    caption: str              # detected caption (may be empty)
    markdown: str             # full markdown representation
    bbox: Optional[Tuple[float, float, float, float]] = None
    rows: int = 0
    cols: int = 0
    source: str = ""          # "structural", "markdown-pipe", or "text-heuristic"


# ---------------------------------------------------------------------------
# Caption pattern  (shared across strategies)
# ---------------------------------------------------------------------------

_TABLE_CAPTION_RE = re.compile(
    r"(?:Table|TAB(?:LE)?)\s*\.?\s*(\d+|[IVXLC]+)[.:\s]?\s*(.*)",
    re.IGNORECASE,
)


# =========================================================================
# Strategy 1 — Structural tables via PyMuPDF find_tables()
# =========================================================================

def _extract_structured_tables(doc: fitz.Document) -> List[ExtractedTable]:
    """Use PyMuPDF's built-in ``find_tables()`` for ruled/bordered tables."""
    tables: List[ExtractedTable] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        try:
            finder = page.find_tables()
        except Exception as exc:
            logger.debug("find_tables failed on page {}: {}", page_idx + 1, exc)
            continue

        for tab_idx, table in enumerate(finder.tables):
            try:
                cells = table.extract()
                if not cells or len(cells) < 2:
                    continue

                cleaned = [[_clean_cell(c) for c in row] for row in cells]
                n_rows = len(cleaned)
                n_cols = max(len(r) for r in cleaned) if cleaned else 0
                for row in cleaned:
                    while len(row) < n_cols:
                        row.append("")

                md = _cells_to_markdown(cleaned)
                caption = _find_table_caption_near_bbox(page, table.bbox)

                tables.append(ExtractedTable(
                    page_number=page_idx + 1,
                    table_index=tab_idx,
                    caption=caption,
                    markdown=md,
                    bbox=table.bbox,
                    rows=n_rows,
                    cols=n_cols,
                    source="structural",
                ))
                logger.debug(
                    "Structural table p{} t{}: {}×{} {}",
                    page_idx + 1, tab_idx, n_rows, n_cols,
                    caption[:60] if caption else "(no caption)",
                )
            except Exception as exc:
                logger.warning("Structural table p{} t{} failed: {}", page_idx + 1, tab_idx, exc)

    return tables


# =========================================================================
# Strategy 2 — Markdown pipe-tables from pymupdf4llm output
# =========================================================================

_PIPE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")
_PIPE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")


def _extract_markdown_pipe_tables(
    markdown_pages: List[str],
    skip_pages: set,
) -> List[ExtractedTable]:
    """Detect Markdown pipe-tables (``| a | b | c |``) in the markdown output."""
    tables: List[ExtractedTable] = []

    for page_idx, page_text in enumerate(markdown_pages):
        if (page_idx + 1) in skip_pages:
            continue

        lines = page_text.split("\n")
        runs = _find_pipe_table_runs(lines)

        for run_start, run_end in runs:
            run_lines = lines[run_start:run_end + 1]
            parsed = _parse_pipe_table(run_lines)
            if parsed is None:
                continue

            caption = _find_caption_above(lines, run_start)

            tables.append(ExtractedTable(
                page_number=page_idx + 1,
                table_index=len(tables),
                caption=caption,
                markdown=parsed,
                rows=run_end - run_start + 1,
                source="markdown-pipe",
            ))

    return tables


def _find_pipe_table_runs(lines: List[str]) -> List[Tuple[int, int]]:
    """Find contiguous blocks of pipe-delimited lines (Markdown tables)."""
    runs: List[Tuple[int, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        if _PIPE_ROW_RE.match(lines[i]):
            start = i
            while i < n and (_PIPE_ROW_RE.match(lines[i]) or _PIPE_SEP_RE.match(lines[i])):
                i += 1
            end = i - 1
            # Need at least header + separator + 1 data row = 3 lines
            if end - start + 1 >= 3:
                runs.append((start, end))
        else:
            i += 1
    return runs


def _parse_pipe_table(lines: List[str]) -> Optional[str]:
    """Parse and re-format a block of Markdown pipe-table lines."""
    rows: List[List[str]] = []
    for line in lines:
        stripped = line.strip()
        # Skip separator lines
        if _PIPE_SEP_RE.match(stripped):
            continue
        # Split on pipe
        cells = [c.strip() for c in stripped.split("|")]
        # Remove empty leading/trailing cells from "|col|col|"
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if cells:
            rows.append(cells)

    if len(rows) < 2:
        return None

    return _cells_to_markdown(rows)


# =========================================================================
# Strategy 3 — Text-heuristic tables (aligned numeric columns)
# =========================================================================

def _extract_text_heuristic_tables(
    markdown_pages: List[str],
    skip_pages: set,
) -> List[ExtractedTable]:
    """Detect tables rendered as whitespace-aligned columns of numbers.

    Works on the markdown output where pymupdf4llm keeps each row's
    numbers on a single line.  Identifies runs of lines with 2+ decimal
    numbers OR 3+ numeric values (int or float).
    """
    tables: List[ExtractedTable] = []

    for page_idx, page_text in enumerate(markdown_pages):
        if (page_idx + 1) in skip_pages:
            continue

        lines = page_text.split("\n")
        runs = _find_numeric_table_runs(lines)

        for run_start, run_end in runs:
            run_lines = lines[run_start:run_end + 1]
            header_candidates = lines[max(0, run_start - 3):run_start]
            parsed = _parse_text_table(header_candidates, run_lines)
            if parsed is None:
                continue

            caption = _find_caption_above(lines, run_start)

            tables.append(ExtractedTable(
                page_number=page_idx + 1,
                table_index=len(tables),
                caption=caption,
                markdown=parsed,
                rows=len(run_lines),
                source="text-heuristic",
            ))

    return tables


def _is_numeric_table_line(line: str) -> bool:
    """Check if a line looks like a table data row with numeric values.

    Criteria (any of):
      - 3+ decimal numbers (0.43, 97.5, etc.)
      - 2+ decimal numbers AND a leading text label
      - 4+ numbers (int or float) separated by whitespace
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 5:
        return False

    # Remove markdown bold markers for analysis
    clean = re.sub(r"\*{1,2}", "", stripped)

    decimals = re.findall(r"(?:^|[\s,(])(\d+\.\d+)(?:[\s,)]|$)", clean)
    integers = re.findall(r"(?:^|[\s,(])(\d{2,})(?:[\s,)]|$)", clean)
    all_nums = len(decimals) + len(integers)

    # Strong signal: 3+ decimal numbers
    if len(decimals) >= 3:
        return True

    # Medium signal: 2+ decimals with a text label (category name)
    if len(decimals) >= 2 and re.match(r"^[A-Za-z]", clean):
        return True

    # Medium signal: 4+ total numbers (handles integer-heavy tables like counts)
    if all_nums >= 4:
        return True

    # Percentage tables: 3+ values like "98.5%" or "98.5 %"
    pcts = re.findall(r"\d+\.?\d*\s*%", clean)
    if len(pcts) >= 3:
        return True

    return False


def _find_numeric_table_runs(
    lines: List[str], min_run: int = 3,
) -> List[Tuple[int, int]]:
    """Find contiguous runs of numeric-table lines, allowing 1-line gaps."""
    flags = [_is_numeric_table_line(ln) for ln in lines]
    runs: List[Tuple[int, int]] = []
    i = 0
    n = len(flags)
    while i < n:
        if flags[i]:
            start = i
            while i < n:
                if flags[i]:
                    i += 1
                elif i + 1 < n and flags[i + 1]:
                    i += 1  # allow 1-line gap (category heading between rows)
                else:
                    break
            end = i - 1
            if (end - start + 1) >= min_run:
                runs.append((start, end))
        else:
            i += 1
    return runs


def _parse_text_table(
    header_candidates: List[str],
    data_lines: List[str],
) -> Optional[str]:
    """Convert whitespace-aligned text-table lines into a Markdown table.

    Handles patterns like:
        Category  0.43 0.57 0.82
    Or:
        Category
        0.43 0.57 0.82          (merged into one row)
    """
    if not data_lines:
        return None

    # Step 1 — merge category labels with subsequent numeric lines
    merged: List[str] = []
    pending_label: Optional[str] = None

    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        clean = re.sub(r"\*{1,2}", "", stripped)

        if _is_numeric_table_line(clean):
            if pending_label:
                merged.append(f"{pending_label}  {clean}")
                pending_label = None
            else:
                merged.append(clean)
        elif re.match(r"^[A-Za-z]", clean) and len(clean.split()) <= 4:
            # Short text-only line → likely a category label
            pending_label = clean
        else:
            if pending_label:
                merged.append(f"{pending_label}  {clean}")
                pending_label = None

    if len(merged) < 2:
        return None

    # Step 2 — split each line into cells
    parsed_rows: List[List[str]] = []
    for line in merged:
        cells = re.split(r"\s{2,}", line)
        cells = [c.strip() for c in cells if c.strip()]
        expanded: List[str] = []
        for cell in cells:
            if re.match(r"^[\d\.\s\-%±]+$", cell) and " " in cell:
                expanded.extend(cell.split())
            else:
                expanded.append(cell)
        if expanded:
            parsed_rows.append(expanded)

    if len(parsed_rows) < 2:
        return None

    # Step 3 — normalise column count
    col_counts = [len(r) for r in parsed_rows]
    target_cols = max(set(col_counts), key=col_counts.count)

    header_row = _detect_column_headers(header_candidates, target_cols)

    normalised: List[List[str]] = []
    if header_row:
        normalised.append(header_row)
    for row in parsed_rows:
        while len(row) < target_cols:
            row.append("-")
        normalised.append(row[:target_cols])

    if len(normalised) < 3:
        return None

    return _cells_to_markdown(normalised)


def _detect_column_headers(
    header_lines: List[str], target_cols: int,
) -> Optional[List[str]]:
    """Extract column header names from lines above the numeric data."""
    for line in reversed(header_lines):
        stripped = line.strip()
        if not stripped or _TABLE_CAPTION_RE.match(stripped):
            continue
        clean = re.sub(r"\*{1,2}", "", stripped).strip()
        parts = re.split(r"\s{2,}", clean)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 3 and abs(len(parts) - target_cols) <= 2:
            while len(parts) < target_cols:
                parts.append("")
            return parts[:target_cols]
    return None


# =========================================================================
# Shared helpers
# =========================================================================

def _clean_cell(cell: Any) -> str:
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"_{1,3}", "", text)
    return text


def _cells_to_markdown(rows: List[List[str]]) -> str:
    """Convert rows → properly aligned Markdown pipe-table."""
    if not rows:
        return ""

    n_cols = max(len(r) for r in rows)
    widths = [3] * n_cols
    for row in rows:
        for j, cell in enumerate(row):
            if j < n_cols:
                widths[j] = max(widths[j], len(cell))

    def _fmt(row: List[str]) -> str:
        parts = []
        for j in range(n_cols):
            cell = row[j] if j < len(row) else ""
            parts.append(f" {cell:<{widths[j]}} ")
        return "|" + "|".join(parts) + "|"

    out = [_fmt(rows[0])]
    out.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for row in rows[1:]:
        out.append(_fmt(row))
    return "\n".join(out)


def _find_table_caption_near_bbox(page: fitz.Page, bbox: Tuple) -> str:
    """Search for a ``Table N:`` caption near a bounding box."""
    x0, y0, x1, y1 = bbox

    for search_rect in [
        fitz.Rect(x0 - 10, max(0, y0 - 60), x1 + 10, y0 + 5),   # above
        fitz.Rect(x0 - 10, y1 - 5, x1 + 10, min(page.rect.height, y1 + 60)),  # below
    ]:
        text = page.get_textbox(search_rect).strip()
        for line in text.split("\n"):
            if _TABLE_CAPTION_RE.match(line.strip()):
                return line.strip()
    return ""


def _find_caption_above(lines: List[str], run_start: int) -> str:
    """Search the few lines above a table run for a ``Table N`` caption."""
    for idx in range(max(0, run_start - 6), run_start):
        m = _TABLE_CAPTION_RE.match(lines[idx].strip())
        if m:
            return lines[idx].strip()
    return ""


# =========================================================================
# Public API
# =========================================================================

def extract_tables(
    pdf_path: str,
    markdown_pages: Optional[List[str]] = None,
) -> List[ExtractedTable]:
    """Extract all tables from a PDF.

    Args:
        pdf_path: Path to the PDF file.
        markdown_pages: Pre-extracted markdown pages from pymupdf4llm.
            Enables pipe-table and text-heuristic detection.  If ``None``,
            only structural (find_tables) extraction is attempted.

    Returns:
        Sorted list of ``ExtractedTable`` objects.
    """
    logger.info("Extracting tables from: {}", pdf_path)
    doc = fitz.open(pdf_path)

    try:
        # 1. Structural tables
        structured = _extract_structured_tables(doc)
        structural_pages = {t.page_number for t in structured}
        logger.info("Structural tables: {}", len(structured))

        pipe_tables: List[ExtractedTable] = []
        text_tables: List[ExtractedTable] = []

        if markdown_pages:
            # 2. Markdown pipe-tables (skip pages with structural tables)
            pipe_tables = _extract_markdown_pipe_tables(markdown_pages, structural_pages)
            pipe_pages = structural_pages | {t.page_number for t in pipe_tables}
            logger.info("Pipe-tables: {}", len(pipe_tables))

            # 3. Text-heuristic tables (skip pages already covered)
            text_tables = _extract_text_heuristic_tables(markdown_pages, pipe_pages)
            logger.info("Text-heuristic tables: {}", len(text_tables))

        all_tables = structured + pipe_tables + text_tables
        all_tables.sort(key=lambda t: (t.page_number, t.table_index))

        logger.info("Total tables extracted: {} (structural={}, pipe={}, heuristic={})",
                     len(all_tables), len(structured), len(pipe_tables), len(text_tables))
        return all_tables

    finally:
        doc.close()


def tables_to_markdown_sections(tables: List[ExtractedTable]) -> List[Dict[str, Any]]:
    """Convert extracted tables into section dicts for the chunking pipeline.

    Each table becomes a section with ``is_table=True`` so the chunker
    keeps it as a single chunk with formatting preserved.
    """
    sections: List[Dict[str, Any]] = []
    for i, table in enumerate(tables):
        title = table.caption if table.caption else f"Table (Page {table.page_number})"
        content = table.markdown
        if table.caption:
            content = f"{table.caption}\n\n{table.markdown}"

        sections.append({
            "title": title,
            "page_start": table.page_number,
            "order": 9000 + i,
            "content": content,
            "is_table": True,
        })

    return sections
