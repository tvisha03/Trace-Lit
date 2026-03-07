from __future__ import annotations

import importlib
import re
import shutil
from pathlib import Path

from shared.utils.export_text import build_export_blocks, format_structured_text

_FORMULA_PATTERN = re.compile(
    r"(\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$)"
)
_TABLE_SEPARATOR_RE = re.compile(r"^\|?[\s:]*-{2,}[\s:]*(?:\|[\s:]*-{2,}[\s:]*)+\|?\s*$")
_LEGACY_PREFIX_RE = re.compile(
    r"^(?:\[(?:Paper:|TABLE,|Caption:|Equation on page|Eq\.)[^\]]*\]\s*)+",
    re.IGNORECASE,
)
_CITATION_TAG_RE = re.compile(r"\[(?:[a-f0-9]{1,8}_)?[PTFE]\d+(?:-S\d+)?\]")
_FORMULA_SIGNAL_RE = re.compile(r"(?:\\[A-Za-z]+|[=<>^_{}]|[∑∏∫∂∇∞≈±÷√∀∃≤≥≠⊗])")
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def strip_export_citation_tags(text: str) -> str:
    cleaned = _CITATION_TAG_RE.sub("", text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _strip_legacy_prefixes(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in (text or "").splitlines():
        normalized = _LEGACY_PREFIX_RE.sub("", line).strip()
        if normalized:
            cleaned_lines.append(normalized)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")
    return "\n".join(cleaned_lines).strip()


def _asset_source_text(asset: dict) -> str:
    source = str(asset.get("raw_content") or asset.get("content") or "")
    source = source.replace("\\r\\n", "\n").replace("\\n", "\n")
    return _strip_legacy_prefixes(source)


def _ensure_output_dir(output_dir: str | Path) -> Path:
    target = Path(output_dir) / "_rendered_assets"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _asset_digest(asset: dict, source: str) -> str:
    payload = (
        f"{asset.get('citation_id', '')}|{asset.get('chunk_type', '')}|{source}"
        .encode("utf-8")
    )
    return importlib.import_module("_sha3").sha3_256(payload).hexdigest()[:12]


def _load_font(size: int):
    ImageFont = importlib.import_module("PIL.ImageFont")

    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _measure_text(draw, text: str, font) -> tuple[int, int]:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=6)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}".strip()
        width, _ = _measure_text(draw, candidate, font)
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_text_card(target_path: Path, title: str, body: str) -> None:
    Image = importlib.import_module("PIL.Image")
    ImageDraw = importlib.import_module("PIL.ImageDraw")

    width = 1400
    padding = 48
    title_font = _load_font(34)
    body_font = _load_font(24)

    draft = Image.new("RGB", (width, 200), "white")
    draw = ImageDraw.Draw(draft)
    wrapped_body = _wrap_text(draw, body, body_font, width - (padding * 2))

    _, title_height = _measure_text(draw, title, title_font)
    body_text = "\n".join(wrapped_body)
    _, body_height = _measure_text(draw, body_text, body_font)
    height = max(260, padding * 3 + title_height + body_height)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, width - 12, height - 12), radius=20, outline="#A7B3C2", width=3)
    draw.text((padding, padding), title, fill="#16324F", font=title_font)
    draw.multiline_text((padding, padding + title_height + 24), body_text, fill="#202020", font=body_font, spacing=8)
    image.save(target_path)


def _render_table_image(target_path: Path, asset: dict) -> bool:
    Image = importlib.import_module("PIL.Image")
    ImageDraw = importlib.import_module("PIL.ImageDraw")

    headers = list(asset.get("table_headers") or [])
    rows = list(asset.get("table_rows") or [])
    if not headers:
        blocks = build_export_blocks(_asset_source_text(asset))
        table_block = next((block for block in blocks if block.kind == "table"), None)
        if table_block:
            headers = list(table_block.headers)
            rows = list(table_block.rows or [])
    if not headers:
        return False

    col_count = len(headers)
    col_width = 280
    row_height = 72
    title_height = 96
    width = max(1100, col_count * col_width)
    height = title_height + (len(rows) + 1) * row_height + 40

    title_font = _load_font(30)
    header_font = _load_font(22)
    cell_font = _load_font(20)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, width - 12, height - 12), radius=18, outline="#6C7A89", width=3)

    title = f"[{asset.get('citation_id', '')}] Table"
    draw.text((32, 28), title, fill="#16324F", font=title_font)

    start_y = title_height
    for col_idx, header in enumerate(headers):
        x0 = col_idx * col_width + 20
        x1 = x0 + col_width
        draw.rectangle((x0, start_y, x1, start_y + row_height), fill="#DCE8F4", outline="#8FA3B8", width=2)
        draw.multiline_text((x0 + 12, start_y + 16), header, fill="#142434", font=header_font, spacing=6)

    for row_idx, row in enumerate(rows, start=1):
        y0 = start_y + row_idx * row_height
        y1 = y0 + row_height
        padded = row + [""] * max(0, col_count - len(row))
        for col_idx, cell in enumerate(padded[:col_count]):
            x0 = col_idx * col_width + 20
            x1 = x0 + col_width
            fill = "#FFFFFF" if row_idx % 2 else "#F7FAFD"
            draw.rectangle((x0, y0, x1, y1), fill=fill, outline="#C3CED9", width=2)
            draw.multiline_text((x0 + 12, y0 + 12), cell, fill="#202020", font=cell_font, spacing=5)

    image.save(target_path)
    return True


def _formula_line_score(line: str) -> int:
    stripped = line.strip()
    if not stripped:
        return 0
    score = 0
    if _FORMULA_SIGNAL_RE.search(stripped):
        score += 5
    score += stripped.count("\\") * 2
    score += sum(1 for char in stripped if char in "=<>^_{}()[]")
    alpha_words = re.findall(r"\b[A-Za-z]{4,}\b", stripped)
    if len(alpha_words) > 5 and "=" not in stripped:
        score -= 4
    return score


def _is_valid_formula_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False

    if "##" in stripped or stripped.endswith(":"):
        return False

    if len(stripped) > 220 and "=" not in stripped and "\\" not in stripped:
        return False

    alpha_words = re.findall(r"\b[A-Za-z]{3,}\b", stripped)
    symbol_hits = len(re.findall(r"[=<>^_{}()\[\]+\-/*]", stripped))
    if _FORMULA_PATTERN.search(stripped):
        return True
    if "=" in stripped and _FORMULA_SIGNAL_RE.search(stripped):
        return True
    if stripped.count("\\") >= 2 and len(alpha_words) <= 6:
        return True
    if symbol_hits >= 4 and len(alpha_words) <= 4 and len(stripped) <= 120:
        return True
    return False


def _extract_formula_text(asset: dict) -> str:
    existing = str(asset.get("formula_text") or "").strip()
    if existing and _is_valid_formula_text(existing):
        return existing

    source = _asset_source_text(asset)
    match = _FORMULA_PATTERN.search(source)
    if match:
        candidate = match.group(1).strip()
        if _is_valid_formula_text(candidate):
            return candidate

    candidates = [line.strip() for line in source.splitlines() if _formula_line_score(line) > 0]
    if candidates:
        candidate = max(candidates, key=_formula_line_score)
        if _is_valid_formula_text(candidate):
            return candidate

    return ""


def _render_formula_image(target_path: Path, asset: dict) -> bool:
    formula = _extract_formula_text(asset)
    if not formula:
        return False
    _render_text_card(target_path, f"[{asset.get('citation_id', '')}] Formula", formula)
    return True


def _render_figure_fallback(target_path: Path, asset: dict) -> bool:
    body = format_structured_text(_asset_source_text(asset))
    if not body:
        return False
    _render_text_card(target_path, f"[{asset.get('citation_id', '')}] Figure", body)
    return True


def _render_missing_asset_image(target_path: Path, asset: dict) -> bool:
    chunk_type = str(asset.get("chunk_type", "")).lower()
    if chunk_type == "table":
        return _render_table_image(target_path, asset)
    if chunk_type == "formula":
        return _render_formula_image(target_path, asset)
    if chunk_type == "figure":
        return _render_figure_fallback(target_path, asset)
    return False


def _extract_asset_description(asset: dict) -> str:
    blocks = build_export_blocks(_asset_source_text(asset))
    parts: list[str] = []
    for block in blocks:
        if block.kind == "table":
            continue
        text = block.text or format_structured_text(_asset_source_text(asset))
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _normalize_pipe_cell(cell: str) -> str:
    return format_structured_text(cell.replace("<br>", "\n")).replace("\n", " ").strip()


def _looks_like_header_row(row: list[str]) -> bool:
    header_terms = (
        "model",
        "method",
        "dimension",
        "dataset",
        "metric",
        "language",
        "generation",
        "speed",
        "efficiency",
        "modality",
        "paper",
    )
    hits = sum(1 for cell in row if any(term in cell.lower() for term in header_terms))
    return hits >= max(2, len(row) // 2)


def _extract_legacy_pipe_table(source: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in (source or "").splitlines() if "|" in line]
    if not lines:
        return [], []

    expected_columns = 0
    for line in lines:
        if _TABLE_SEPARATOR_RE.match(line):
            expected_columns = max(
                expected_columns,
                len([part for part in line.strip().strip("|").split("|") if part.strip()]),
            )

    parsed_rows: list[list[str]] = []
    for line in lines:
        if _TABLE_SEPARATOR_RE.match(line):
            continue

        raw_cells = [part.strip() for part in line.strip().strip("|").split("|")]
        cleaned_cells = [_normalize_pipe_cell(cell) for cell in raw_cells if cell.strip()]
        if not cleaned_cells:
            continue

        if expected_columns and len(cleaned_cells) > expected_columns:
            for start in range(0, len(cleaned_cells), expected_columns):
                group = cleaned_cells[start:start + expected_columns]
                if len(group) == expected_columns:
                    parsed_rows.append(group)
        elif not expected_columns or len(cleaned_cells) == expected_columns:
            parsed_rows.append(cleaned_cells)

    if not parsed_rows:
        return [], []

    if expected_columns:
        parsed_rows = [row for row in parsed_rows if len(row) == expected_columns]
        if not parsed_rows:
            return [], []

    headers = parsed_rows[0]
    rows = parsed_rows[1:]
    if not rows or not _looks_like_header_row(headers):
        headers = ["Model", *[f"Column {idx}" for idx in range(2, len(parsed_rows[0]) + 1)]]
        rows = parsed_rows

    return headers, rows


def _extract_table_payload(asset: dict) -> tuple[list[str], list[list[str]]]:
    source = _asset_source_text(asset)
    headers, rows = _extract_legacy_pipe_table(source)
    if headers:
        return headers, rows

    blocks = build_export_blocks(source)
    for block in blocks:
        if block.kind == "table" and block.headers:
            return list(block.headers), [list(row) for row in block.rows]
    return [], []


def _copy_asset_image(source_path: str, render_dir: Path, asset: dict, source: str) -> Path | None:
    source_file = Path(source_path)
    if not source_file.exists():
        return None

    suffix = source_file.suffix or ".png"
    digest = _asset_digest(asset, source)
    target_path = render_dir / f"{asset.get('citation_id', 'asset')}_{digest}{suffix}"
    if not target_path.exists():
        shutil.copy2(source_file, target_path)
    return target_path


def prepare_cited_assets(cited_assets: list[dict] | None, output_dir: str | Path) -> list[dict]:
    if not cited_assets:
        return []

    output_root = Path(output_dir)
    render_dir = _ensure_output_dir(output_dir)
    prepared: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for asset in cited_assets:
        normalized = dict(asset)
        source = _asset_source_text(normalized)
        normalized["raw_content"] = source
        normalized["content"] = format_structured_text(source)
        headers, rows = _extract_table_payload(normalized)
        if headers:
            normalized["table_headers"] = headers
            normalized["table_rows"] = rows
        description = _extract_asset_description(normalized)
        if description:
            normalized["description"] = description
        formula_text = _extract_formula_text(normalized)
        if formula_text:
            normalized["formula_text"] = formula_text

        dedupe_key = (
            str(normalized.get("paper_title", "")),
            str(normalized.get("citation_id", "")),
            str(normalized.get("chunk_type", "")),
            _asset_digest(normalized, source),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        image_path = normalized.get("image_path")
        copied_image: Path | None = None
        if image_path and Path(image_path).exists():
            copied_image = _copy_asset_image(str(image_path), render_dir, normalized, source)
        if str(normalized.get("chunk_type", "")).lower() == "formula" and not copied_image and not formula_text:
            continue
        if copied_image and copied_image.exists():
            normalized["image_path"] = str(copied_image)
            normalized["image_rel_path"] = copied_image.relative_to(output_root).as_posix()
            prepared.append(normalized)
            continue

        digest = _asset_digest(normalized, source)
        target_path = render_dir / f"{normalized.get('citation_id', 'asset')}_{digest}.png"
        if target_path.exists() or _render_missing_asset_image(target_path, normalized):
            normalized["image_path"] = str(target_path)
            normalized["image_rel_path"] = target_path.relative_to(output_root).as_posix()

        prepared.append(normalized)
    return prepared
