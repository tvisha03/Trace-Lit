import re
from pathlib import Path
from dataclasses import dataclass

from shared.logger import get_logger

logger = get_logger(__name__)

_MD_TABLE_PATTERN = re.compile(
    r"((?:^\|.+\|[ \t]*\n){2,})",
    re.MULTILINE,
)

_SEPARATOR_ROW = re.compile(r"^\|[\s\-:|]+\|$")

_CAPTION_PATTERN = re.compile(
    r"(?:Table|TABLE)\s+(\d+)[.:]?\s*(.*)",
    re.IGNORECASE,
)

_SYMBOL_ONLY = re.compile(r"^[\s✓✗×☑☐●○◯■□▪▫\-–—|,.\d<>br/\s]+$")


@dataclass
class ExtractedTable:
    content: str
    page_number: int
    caption: str = ""
    row_count: int = 0
    col_count: int = 0
    bbox: tuple[float, float, float, float] | None = None
    table_number: int | None = None


def _extract_data_rows(markdown_table: str) -> list[str]:
    lines = [ln for ln in markdown_table.strip().split("\n") if ln.strip()]
    return [ln for ln in lines if not _SEPARATOR_ROW.match(ln.strip())]


def _compute_text_ratio(data_rows: list[str]) -> float:
    total_cells = 0
    text_cells = 0
    for row in data_rows:
        cells = [c.strip() for c in row.split("|")[1:-1]]
        for cell in cells:
            total_cells += 1
            cleaned = re.sub(r"[\s✓✗×☑☐●○◯■□▪▫\-–—<>br/]", "", cell)
            if len(cleaned) > 1:
                text_cells += 1
    return text_cells / total_cells if total_cells > 0 else 0.0


def _get_all_cell_text(data_rows: list[str]) -> str:
    return " ".join(
        c.strip()
        for row in data_rows
        for c in row.split("|")[1:-1]
    )


def _count_table_dimensions(markdown_table: str) -> tuple[int, int]:
    data_rows = _extract_data_rows(markdown_table)
    row_count = len(data_rows)
    col_count = 0
    if data_rows:
        col_count = data_rows[0].count("|") - 1
        col_count = max(col_count, 1)
    return row_count, col_count


def _has_meaningful_content(markdown_table: str) -> bool:
    data_rows = _extract_data_rows(markdown_table)
    if _compute_text_ratio(data_rows) < 0.15:
        return False
    return not _SYMBOL_ONLY.match(_get_all_cell_text(data_rows))


def _find_caption_near(text: str, table_start: int) -> str:
    search_start = max(0, table_start - 300)
    preceding = text[search_start:table_start]

    lines = preceding.strip().split("\n")
    for line in reversed(lines[-5:]):
        match = _CAPTION_PATTERN.search(line.strip())
        if match:
            return f"Table {match.group(1)}: {match.group(2)}".strip().rstrip(":")
    return ""


def extract_tables_from_text(
    markdown_text: str,
    default_page: int = 0,
) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    table_number = 0

    for match in _MD_TABLE_PATTERN.finditer(markdown_text):
        raw = match.group(1).strip()
        rows, cols = _count_table_dimensions(raw)

        if rows < 2 or cols < 2:
            continue

        if not _has_meaningful_content(raw):
            continue

        table_number += 1
        caption = _find_caption_near(markdown_text, match.start())

        tables.append(ExtractedTable(
            content=raw,
            page_number=default_page,
            caption=caption or f"Table {table_number}",
            row_count=rows,
            col_count=cols,
            table_number=table_number,
        ))

    return tables


def _validate_table_content(content: str) -> tuple[int, int] | None:
    if not content or len(content.strip()) < 10:
        return None
    rows, cols = _count_table_dimensions(content)
    if rows < 2 or cols < 2:
        return None
    if not _has_meaningful_content(content):
        return None
    return rows, cols


def _extract_bbox(raw_table: dict) -> tuple[float, float, float, float] | None:
    bbox_raw = raw_table.get("bbox")
    if bbox_raw and len(bbox_raw) >= 4:
        return tuple(bbox_raw)
    return None


def _process_raw_table(
    raw_table: dict | list,
    page_num: int,
    table_counter: dict,
) -> ExtractedTable | None:
    if not isinstance(raw_table, dict):
        return None
    content = raw_table.get("content", raw_table.get("markdown", ""))
    dims = _validate_table_content(content)
    if not dims:
        return None
    rows, cols = dims
    table_counter["count"] += 1
    return ExtractedTable(
        content=content.strip(),
        page_number=page_num,
        caption=raw_table.get("caption", f"Table {table_counter['count']}"),
        row_count=rows,
        col_count=cols,
        bbox=_extract_bbox(raw_table),
        table_number=table_counter["count"],
    )


def _deduplicate_tables(tables: list[ExtractedTable]) -> list[ExtractedTable]:
    seen: set[str] = set()
    deduplicated: list[ExtractedTable] = []
    for t in tables:
        key = t.content[:200].strip()
        if key not in seen:
            seen.add(key)
            deduplicated.append(t)
    return deduplicated


def extract_tables_from_pages(
    pages: list,
) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    table_counter = {"count": 0}

    for page in pages:
        page_num = getattr(page, "page_number", 0)
        page_text = getattr(page, "text", "")

        text_tables = extract_tables_from_text(page_text, default_page=page_num)
        for t in text_tables:
            table_counter["count"] += 1
            t.table_number = table_counter["count"]
            tables.append(t)

        for raw_table in getattr(page, "tables", []):
            processed = _process_raw_table(raw_table, page_num, table_counter)
            if processed:
                tables.append(processed)

    deduplicated = _deduplicate_tables(tables)
    logger.info(f"Extracted {len(deduplicated)} tables ({len(tables) - len(deduplicated)} duplicates removed)")
    return deduplicated


def _process_pdf_table(
    tab,
    page_idx: int,
    table_counter: dict,
) -> ExtractedTable | None:
    try:
        md = tab.to_markdown()
    except Exception:
        return None
    dims = _validate_table_content(md)
    if not dims:
        return None
    rows, cols = dims
    table_counter["count"] += 1
    bbox = tuple(tab.bbox[:4]) if hasattr(tab, "bbox") and tab.bbox else None
    return ExtractedTable(
        content=md.strip(),
        page_number=page_idx,
        caption=f"Table {table_counter['count']}",
        row_count=rows,
        col_count=cols,
        bbox=bbox,
        table_number=table_counter["count"],
    )


def extract_tables_from_pdf(file_path: str | Path) -> list[ExtractedTable]:
    import pymupdf

    file_path = Path(file_path)
    if not file_path.exists():
        return []

    tables: list[ExtractedTable] = []
    table_counter = {"count": 0}

    doc = pymupdf.open(str(file_path))
    try:
        for page_idx, page in enumerate(doc):
            try:
                tab_finder = page.find_tables(strategy="lines_strict")
            except Exception as exc:
                logger.warning(f"Table detection failed on page {page_idx}: {exc}")
                continue

            for tab in tab_finder.tables:
                processed = _process_pdf_table(tab, page_idx, table_counter)
                if processed:
                    tables.append(processed)
    finally:
        doc.close()

    logger.info(f"Extracted {len(tables)} tables via pymupdf find_tables from {file_path.name}")
    return tables


def merge_tables(
    text_tables: list[ExtractedTable],
    pdf_tables: list[ExtractedTable],
) -> list[ExtractedTable]:
    seen: set[str] = set()
    merged: list[ExtractedTable] = []

    for t in text_tables:
        key = t.content[:200].strip()
        if key not in seen:
            seen.add(key)
            merged.append(t)

    for t in pdf_tables:
        key = t.content[:200].strip()
        if key not in seen:
            seen.add(key)
            merged.append(t)

    for idx, t in enumerate(merged):
        t.table_number = idx + 1

    logger.info(f"Merged tables: {len(text_tables)} text + {len(pdf_tables)} pdf → {len(merged)} unique")
    return merged
