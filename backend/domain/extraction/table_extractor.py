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
    return " ".join(c.strip() for row in data_rows for c in row.split("|")[1:-1])


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

        tables.append(
            ExtractedTable(
                content=raw,
                page_number=default_page,
                caption=caption or f"Table {table_number}",
                row_count=rows,
                col_count=cols,
                table_number=table_number,
            )
        )

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

    # Get raw bbox as tuple (if available)
    bbox_tuple = _extract_box(raw_table)

    # Always standardize to dict format for consistent chunk access
    bbox_dict = {
        "source_type": "table",
        "table_id": f"table_{page_num}_{table_counter['count']}",
        "page": page_num,
        "table_bbox": bbox_tuple,
        "row_bboxes": [],  # No PDF-native row detection for raw tables
        "header_bbox": None,
        "caption_bbox": None,
        "caption_text": raw_table.get("caption", f"Table {table_counter['count']}"),
        "table_number": table_counter["count"],
        "row_indices": list(range(rows)),
    }

    return ExtractedTable(
        content=content.strip(),
        page_number=page_num,
        caption=raw_table.get("caption", f"Table {table_counter['count']}"),
        row_count=rows,
        col_count=cols,
        bbox=bbox_dict,  # Always dict now
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


def _extract_box_text(box: dict, page_text: str) -> str | None:
    if not isinstance(box, dict) or box.get("class") != "table":
        return None
    pos = box.get("pos")
    if not pos or len(pos) < 2:
        return None
    raw = page_text[pos[0] : pos[1]].strip()
    return raw if len(raw) >= 10 else None


def _extract_box_bbox(box: dict) -> tuple | None:
    bbox_raw = box.get("bbox")
    if bbox_raw and len(bbox_raw) >= 4:
        return tuple(bbox_raw[:4])
    return None


def _parse_table_box(
    box: dict,
    page_text: str,
) -> tuple[str, int, int, tuple | None, str | None] | None:
    raw = _extract_box_text(box, page_text)
    if not raw:
        return None
    dims = _validate_table_content(raw)
    if not dims:
        return None
    pos = box.get("pos")
    caption = _find_caption_near(page_text, pos[0])
    return raw, dims[0], dims[1], _extract_box_bbox(box), caption


def _extract_box_tables(page, table_counter: dict) -> list[ExtractedTable]:
    page_boxes = getattr(page, "page_boxes", None) or []
    page_text = getattr(page, "text", "")
    page_num = getattr(page, "page_number", 0)
    tables: list[ExtractedTable] = []

    for box in page_boxes:
        parsed = _parse_table_box(box, page_text)
        if not parsed:
            continue
        raw, rows, cols, bbox, caption = parsed
        table_counter["count"] += 1
        tables.append(
            ExtractedTable(
                content=raw,
                page_number=page_num,
                caption=caption or f"Table {table_counter['count']}",
                row_count=rows,
                col_count=cols,
                bbox=bbox,
                table_number=table_counter["count"],
            )
        )

    return tables


def extract_tables_from_pages(
    pages: list,
) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    table_counter = {"count": 0}

    for page in pages:
        page_num = getattr(page, "page_number", 0)
        page_text = getattr(page, "text", "")

        box_tables = _extract_box_tables(page, table_counter)
        tables.extend(box_tables)

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
    logger.info(
        f"Extracted {len(deduplicated)} tables ({len(tables) - len(deduplicated)} duplicates removed)"
    )
    return deduplicated


def _process_pdf_table(
    tab,
    page_idx: int,
    table_counter: dict,
) -> ExtractedTable | None:
    try:
        # MuPDF's tab.to_markdown() is preferred for clean output
        md = tab.to_markdown()
        if not md:
            return None
    except Exception:
        return None
    dims = _validate_table_content(md)
    if not dims:
        return None
    rows, cols = dims
    table_counter["count"] += 1
    # Convert 0-indexed page_idx to 1-based page_number
    page_number = page_idx + 1

    table_bbox = tuple(tab.bbox[:4]) if hasattr(tab, "bbox") and tab.bbox else None
    row_bboxes = []
    header_bbox = None

    if hasattr(tab, "cells") and tab.cells:
        from collections import defaultdict

        row_coords = defaultdict(list)
        for cell in tab.cells:
            if isinstance(cell, (list, tuple)) and len(cell) >= 3:
                r_idx = cell[0]
                box = cell[2]
                if isinstance(box, (list, tuple)) and len(box) >= 4:
                    row_coords[r_idx].append(box)
            elif hasattr(cell, "rect"):
                r_idx = getattr(cell, "row", 0)
                b = cell.rect
                row_coords[r_idx].append((b.x0, b.y0, b.x1, b.y1))

        for r_idx in sorted(row_coords.keys()):
            boxes = row_coords[r_idx]
            min_x = min(b[0] for b in boxes)
            min_y = min(b[1] for b in boxes)
            max_x = max(b[2] for b in boxes)
            max_y = max(b[3] for b in boxes)
            row_bboxes.append((min_x, min_y, max_x, max_y))

    if not row_bboxes and table_bbox:
        min_x, min_y, max_x, max_y = table_bbox
        row_h = (max_y - min_y) / max(1, rows)
        for i in range(rows):
            row_bboxes.append(
                (min_x, min_y + i * row_h, max_x, min_y + (i + 1) * row_h)
            )

    if row_bboxes:
        header_bbox = row_bboxes[0]

    caption_bbox = None
    if table_bbox:
        min_x, min_y, max_x, max_y = table_bbox
        caption_bbox = (min_x, max_y + 5, max_x, max_y + 35)

    bbox_dict = {
        "source_type": "table",
        "table_id": f"table_{page_number}_{table_counter['count']}",
        "page": page_number,
        "table_bbox": table_bbox,
        "header_bbox": header_bbox,
        "row_bboxes": row_bboxes,
        "caption_bbox": caption_bbox,
        "caption_text": f"Table {table_counter['count']}",
        "table_number": table_counter["count"],
        "row_indices": list(range(1, max(1, rows))),
    }

    return ExtractedTable(
        content=md.strip(),
        page_number=page_number,
        caption=f"Table {table_counter['count']}",
        row_count=rows,
        col_count=cols,
        bbox=bbox_dict,
        table_number=table_counter["count"],
    )


def extract_tables_from_pdf(file_path: str | Path) -> list[ExtractedTable]:
    import pymupdf

    file_path = Path(file_path)
    if not file_path.exists():
        return []

    tables: list[ExtractedTable] = []
    table_counter = {"count": 0}

    try:
        doc = pymupdf.open(str(file_path))
    except Exception as exc:
        logger.warning(f"Could not open PDF for table extraction: {exc}")
        return []

    try:
        for page_idx, page in enumerate(doc):
            found = _find_tables_safe(page, page_idx)
            for tab in found:
                # _process_pdf_table now correctly converts page_idx to 1-based
                processed = _process_pdf_table(tab, page_idx, table_counter)
                if processed:
                    tables.append(processed)
    finally:
        doc.close()

    logger.info(
        f"Extracted {len(tables)} tables via pymupdf find_tables from {file_path.name}"
    )
    return tables


def _find_tables_safe(page, page_idx: int) -> list:
    for strategy in ("lines_strict", "lines", "text"):
        try:
            tab_finder = page.find_tables(strategy=strategy)
            return list(tab_finder.tables)
        except Exception as exc:
            logger.debug(f"find_tables({strategy}) failed page {page_idx}: {exc}")
            continue
    return []


def merge_tables(
    text_tables: list[ExtractedTable],
    pdf_tables: list[ExtractedTable],
) -> list[ExtractedTable]:
    # Use content prefix as key to identify duplicates
    merged_map: dict[str, ExtractedTable] = {}

    for t in text_tables:
        key = t.content[:200].strip()
        if key not in merged_map:
            merged_map[key] = t

    for t in pdf_tables:
        key = t.content[:200].strip()
        if key not in merged_map:
            merged_map[key] = t
        else:
            # If we already have it, prefer the one with a bbox
            existing = merged_map[key]
            if not existing.bbox and t.bbox:
                merged_map[key] = t

    merged = list(merged_map.values())
    # Sort by page then position to keep order logical
    merged.sort(
        key=lambda x: (
            x.page_number,
            x.bbox.get("table_bbox", (0, 0, 0, 0))[1]
            if isinstance(x.bbox, dict)
            else (x.bbox[1] if x.bbox else 0),
        )
    )

    for idx, t in enumerate(merged):
        t.table_number = idx + 1

    logger.info(
        f"Merged tables: {len(text_tables)} text + {len(pdf_tables)} pdf → {len(merged)} unique"
    )
    return merged
