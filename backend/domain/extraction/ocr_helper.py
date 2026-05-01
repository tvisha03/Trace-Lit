import re
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

_AFFILIATION_MARKERS = re.compile(
    r"university|institute|department|school|college|lab|center|centre|"
    r"faculty|hospital|inc\.|corp\.|ltd\.|@|\.edu|\.ac\.|\.org",
    re.IGNORECASE,
)

_SINGLE_COMPANY = re.compile(
    r"^(?:apple|google|meta|openai|microsoft|amazon|nvidia|"
    r"deepmind|anthropic|ibm|intel|adobe|samsung|huawei)$",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

_MD_IMAGE_CHECK = re.compile(
    r"!\[.*?\]\(.+?\)|==> picture .* intentionally omitted <=="
)

_OCR_DPI = 600
_BBOX_MARGIN = 15

def _load_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
        return RapidOCR()
    except ImportError:
        logger.info("RapidOCR not available — OCR author extraction disabled")
        return None

def _has_image_content(box: dict, text: str) -> bool:
    pos = box.get("pos", (0, 0))
    if len(pos) < 2:
        return False
    raw = text[pos[0]:pos[1]].strip()
    return bool(_MD_IMAGE_CHECK.search(raw)) or box.get("class") == "picture"

def _get_title_end_pos(boxes: list[dict]) -> int:
    title_end = 0
    for box in boxes:
        if box.get("class") == "title":
            pos = box.get("pos", (0, 0))
            if len(pos) >= 2:
                title_end = max(title_end, pos[1])

    if title_end == 0 and boxes:
        first_pos = boxes[0].get("pos", (0, 0))
        title_end = first_pos[1] if len(first_pos) >= 2 else 0
    return title_end

def _get_abstract_start_pos(
    boxes: list[dict], text: str, title_end: int,
) -> int:
    for box in boxes:
        pos = box.get("pos", (0, 0))
        if len(pos) < 2 or pos[0] <= title_end:
            continue
        raw = text[pos[0]:pos[1]].strip()
        if re.search(r"\babstract\b", raw, re.IGNORECASE):
            return pos[0]
    return len(text)

def _find_author_region(pages: list) -> list[dict] | None:
    if not pages:
        return None
    page = pages[0]
    boxes = getattr(page, "page_boxes", None) or []
    text = getattr(page, "text", "")
    if not boxes:
        return None

    title_end = _get_title_end_pos(boxes)
    abstract_start = _get_abstract_start_pos(boxes, text, title_end)

    candidates = [
        box for box in boxes
        if _is_candidate_box(box, text, title_end, abstract_start)
    ]
    return candidates if candidates else None

def _is_candidate_box(
    box: dict, text: str, title_end: int, abstract_start: int,
) -> bool:
    pos = box.get("pos", (0, 0))
    if len(pos) < 2:
        return False
    return pos[0] >= title_end and pos[0] < abstract_start and _has_image_content(box, text)

def _extract_bbox_list(candidate_boxes: list[dict]) -> list:
    return [b.get("bbox") for b in candidate_boxes if b.get("bbox")]

def _compute_combined_bbox(
    candidate_boxes: list[dict],
    page_width: float,
) -> tuple[float, float, float, float] | None:
    bboxes = _extract_bbox_list(candidate_boxes)
    if not bboxes:
        return None

    x_margin = _BBOX_MARGIN * 8
    y0 = max(0, min(b[1] for b in bboxes) - _BBOX_MARGIN)
    y1 = max(b[3] for b in bboxes) + _BBOX_MARGIN
    x0 = max(0, min(b[0] for b in bboxes) - x_margin)
    x1 = min(page_width, max(b[2] for b in bboxes) + x_margin)

    too_small = (x1 - x0 < 50) or (y1 - y0 < 10)
    return None if too_small else (x0, y0, x1, y1)

def _render_region(doc_page, bbox: tuple) -> bytes | None:
    import pymupdf  # type: ignore[import-untyped]

    rect = pymupdf.Rect(bbox)
    if rect.is_empty or rect.is_infinite:
        return None
    pix = doc_page.get_pixmap(clip=rect, dpi=_OCR_DPI)
    return pix.tobytes("png")

_ROW_Y_THRESHOLD = 50
_NAME_GAP_THRESHOLD = 100

def _ocr_image_bytes(engine, img_bytes: bytes) -> list[tuple]:
    result, _ = engine(img_bytes)
    if not result:
        return []
    return result

def _clean_word(word: str) -> str:
    cleaned = _EMAIL_PATTERN.sub("", word)
    cleaned = re.sub(r"[\d†‡§¶∗◦·•\[\]{}<>]", "", cleaned)
    cleaned = re.sub(r"\*+[a-zA-Z]?", "", cleaned)
    return cleaned.strip()

def _group_into_rows(detections: list[tuple]) -> list[list[tuple]]:
    if not detections:
        return []

    items = []
    for det in detections:
        bbox, text = det[0], det[1]
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        x_left = bbox[0][0]
        x_right = bbox[2][0]
        items.append((y_center, x_left, x_right, text))

    items.sort(key=lambda i: i[0])
    rows: list[list[tuple]] = []
    current_row: list[tuple] = [items[0]]
    current_y = items[0][0]

    for item in items[1:]:
        if abs(item[0] - current_y) <= _ROW_Y_THRESHOLD:
            current_row.append(item)
        else:
            rows.append(current_row)
            current_row = [item]
            current_y = item[0]
    rows.append(current_row)
    return rows

def _is_valid_name(name: str) -> bool:
    if not name or len(name) < 3:
        return False
    if _SINGLE_COMPANY.match(name):
        return False
    return not _AFFILIATION_MARKERS.search(name)

def _group_words_by_gap(sorted_row: list[tuple]) -> list[list[str]]:
    groups: list[list[str]] = []
    current_group: list[str] = [_clean_word(sorted_row[0][3])]
    prev_right = sorted_row[0][2]

    for item in sorted_row[1:]:
        gap = item[1] - prev_right
        word = _clean_word(item[3])
        if gap < _NAME_GAP_THRESHOLD:
            current_group.append(word)
        else:
            groups.append(current_group)
            current_group = [word]
        prev_right = item[2]
    groups.append(current_group)
    return groups

def _merge_row_into_names(row: list[tuple]) -> list[str]:
    sorted_row = sorted(row, key=lambda i: i[1])
    groups = _group_words_by_gap(sorted_row)

    names: list[str] = []
    for group in groups:
        name = " ".join(w for w in group if w).strip()
        if _is_valid_name(name):
            names.append(name)
    return names

def _extract_names_from_detections(detections: list[tuple]) -> list[str]:
    if not detections:
        return []

    rows = _group_into_rows(detections)
    names: list[str] = []
    for row in rows:
        row_names = _merge_row_into_names(row)
        names.extend(row_names)
    return names

def _ocr_page_region(file_path: Path, candidate_boxes: list[dict]) -> list[tuple]:
    import pymupdf  # type: ignore[import-untyped]

    engine = _load_ocr_engine()
    if engine is None:
        return []

    doc = pymupdf.open(str(file_path))
    try:
        if len(doc) == 0:
            return []
        doc_page = doc[0]
        combined = _compute_combined_bbox(candidate_boxes, doc_page.rect.width)
        if not combined:
            return []
        img_bytes = _render_region(doc_page, combined)
        if not img_bytes:
            return []
        return _ocr_image_bytes(engine, img_bytes)
    finally:
        doc.close()

def ocr_author_region(
    file_path: str | Path,
    pages: list,
) -> str | None:
    file_path = Path(file_path)
    if not file_path.exists():
        return None

    candidate_boxes = _find_author_region(pages)
    if not candidate_boxes:
        return None

    detections = _ocr_page_region(file_path, candidate_boxes)
    names = _extract_names_from_detections(detections)
    if not names:
        return None

    result = "; ".join(names)
    logger.info(f"OCR-extracted authors: {result!r:.200}")
    return result
