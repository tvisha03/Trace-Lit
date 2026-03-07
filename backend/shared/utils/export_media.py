from __future__ import annotations

import importlib
import re
from pathlib import Path

from shared.utils.export_text import build_export_blocks, format_structured_text

_FORMULA_PATTERN = re.compile(
    r"(\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$)"
)
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _asset_source_text(asset: dict) -> str:
    source = str(asset.get("raw_content") or asset.get("content") or "")
    return source.replace("\\r\\n", "\n").replace("\\n", "\n")


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

    blocks = build_export_blocks(_asset_source_text(asset))
    table_block = next((block for block in blocks if block.kind == "table"), None)
    if not table_block or not table_block.headers:
        return False

    headers = table_block.headers
    rows = table_block.rows or []
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


def _extract_formula_text(asset: dict) -> str:
    source = _asset_source_text(asset)
    match = _FORMULA_PATTERN.search(source)
    if match:
        return match.group(1).strip()
    return format_structured_text(source)


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


def prepare_cited_assets(cited_assets: list[dict] | None, output_dir: str | Path) -> list[dict]:
    if not cited_assets:
        return []

    render_dir = _ensure_output_dir(output_dir)
    prepared: list[dict] = []
    for asset in cited_assets:
        normalized = dict(asset)
        image_path = normalized.get("image_path")
        if image_path and Path(image_path).exists():
            prepared.append(normalized)
            continue

        source = _asset_source_text(normalized)
        digest = _asset_digest(normalized, source)
        target_path = render_dir / f"{normalized.get('citation_id', 'asset')}_{digest}.png"
        if target_path.exists() or _render_missing_asset_image(target_path, normalized):
            normalized["image_path"] = str(target_path)

        prepared.append(normalized)
    return prepared
