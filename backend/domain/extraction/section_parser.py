import re
from dataclasses import dataclass
from re import Match

from shared.logger import get_logger

logger = get_logger(__name__)

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_NUMBERED_HEADING = re.compile(
    r"^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s:,\-–—]+)$", re.MULTILINE
)
_ROMAN_HEADING = re.compile(
    r"^([IVXLC]+)[.\)]\s+([A-Z][A-Za-z\s:,\-–—]+)$", re.MULTILINE
)
_CHAPTER_HEADING = re.compile(
    r"^(?:Chapter|CHAPTER)\s+(\d+|[IVXLC]+|[A-Za-z]+)"
    r"(?:\s*[:.–—]\s*|\s+)([A-Z][A-Za-z\s:,\-–—]+)$",
    re.MULTILINE,
)
_ALLCAPS_HEADING = re.compile(
    r"^([A-Z][A-Z\s]{2,50})$", re.MULTILINE
)
_BOLD_NUMBERED_SPLIT = re.compile(
    r"^\*{2}(\d+(?:\.\d+)*|[IVXLC]+|[A-Z])[.\)\s]*\*{2}\s*\*{2}([^*\n]+)\*{2}\s*$",
    re.MULTILINE,
)
_BOLD_NUMBERED_SINGLE = re.compile(
    r"^\*{2}(\d+(?:\.\d+)*|[IVXLC]+|[A-Z])[.\)\s]+([A-Z][^*\n]+)\*{2}\s*$",
    re.MULTILINE,
)
_BOLD_NAMED_SECTION = re.compile(
    r"^\*{2}([A-Z][A-Za-z\s]{2,60})\*{2}\s*$",
    re.MULTILINE,
)

_KNOWN_SECTIONS = {
    "abstract", "introduction", "background", "related work", "related works",
    "methodology", "methods", "method", "approach", "proposed method",
    "experimental setup", "experiments", "experiment", "evaluation",
    "results", "result", "discussion", "analysis",
    "conclusion", "conclusions", "summary", "future work",
    "references", "bibliography", "acknowledgments", "acknowledgements",
    "appendix", "appendices", "supplementary material",
    "literature review", "theoretical framework", "data collection",
    "findings", "implications", "limitations", "recommendations",
    "case study", "case studies", "implementation", "design",
    "overview", "problem statement", "research questions",
    "materials and methods", "procedures", "ethical considerations",
    "table of contents", "list of figures", "list of tables",
    "dedication", "preface", "glossary", "abbreviations",
    "executive summary", "scope", "objectives", "contributions",
}

@dataclass
class Section:
    title: str
    content: str
    level: int = 1
    page_start: int | None = None
    order: int = 0

def _is_title_case_heading(text: str) -> bool:
    words = text.split()
    if len(words) > 8:
        return False
    long_words = [w for w in words if len(w) > 3]
    return len(long_words) >= 1 and all(w[0].isupper() for w in long_words)

def _is_plausible_section_name(text: str) -> bool:
    cleaned = text.strip()
    if cleaned.lower() in _KNOWN_SECTIONS:
        return True
    if cleaned.isupper():
        return len(cleaned) <= 60
    return _is_title_case_heading(cleaned)

def _find_bold_headings(markdown_text: str) -> list[Match]:
    headings = list(_BOLD_NUMBERED_SPLIT.finditer(markdown_text))
    if len(headings) >= 2:
        return headings
    headings = list(_BOLD_NUMBERED_SINGLE.finditer(markdown_text))
    if len(headings) >= 2:
        return headings
    all_named = list(_BOLD_NAMED_SECTION.finditer(markdown_text))
    return [h for h in all_named if _is_plausible_section_name(h.group(1).strip())]

def _filter_allcaps_headings(matches: list[Match]) -> list[Match]:
    return [
        m for m in matches
        if _is_plausible_section_name(m.group(1).strip())
        and not _is_likely_person_name(m.group(1).strip().title())
    ]

def _find_headings(markdown_text: str) -> list[Match]:
    headings = list(_MD_HEADING.finditer(markdown_text))
    if headings:
        return headings

    chap = list(_CHAPTER_HEADING.finditer(markdown_text))
    if chap:
        return chap

    headings = list(_NUMBERED_HEADING.finditer(markdown_text))
    if headings:
        return headings

    roman = list(_ROMAN_HEADING.finditer(markdown_text))
    if len(roman) >= 2:
        return roman

    bold = _find_bold_headings(markdown_text)
    if bold:
        return bold

    caps = _filter_allcaps_headings(list(_ALLCAPS_HEADING.finditer(markdown_text)))
    if len(caps) >= 3:
        return caps

    return []

def _extract_box_heading_text(text: str, start: int, stop: int) -> str:
    raw = text[start:stop].strip()
    raw = re.sub(r"^#+\s*", "", raw)
    raw = raw.strip("*").strip()
    raw = re.sub(r"^\d+(\.\d+)*[.\)\s]+", "", raw).strip()
    return raw

_SECTION_NUM_PREFIX = re.compile(
    r"^(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])[\s.)]+",
)

_PERSON_NAME_PATTERN = re.compile(
    r"^(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})$",
)

def _is_likely_person_name(text: str) -> bool:
    cleaned = text.strip()
    if cleaned.lower() in _KNOWN_SECTIONS:
        return False
    if _SECTION_NUM_PREFIX.match(cleaned):
        return False
    if len(cleaned.split()) > 5:
        return False
    return bool(_PERSON_NAME_PATTERN.match(cleaned))

def _parse_single_box(box: dict, page_text: str, page_num: int) -> dict | None:
    if not isinstance(box, dict):
        return None
    cls = box.get("class", "")
    if cls not in ("section-header", "title"):
        return None
    pos = box.get("pos")
    if not pos or len(pos) < 2:
        return None
    heading_text = _extract_box_heading_text(page_text, pos[0], pos[1])
    if not heading_text or len(heading_text) < 2:
        return None
    if _is_likely_person_name(heading_text):
        return None
    return {"text": heading_text, "class": cls, "page": page_num, "pos_start": pos[0]}

def _collect_header_boxes(pages: list) -> list[dict]:
    boxes: list[dict] = []
    for page in pages:
        page_boxes = getattr(page, "page_boxes", None) or []
        page_num = getattr(page, "page_number", 0)
        page_text = getattr(page, "text", "")
        for box in page_boxes:
            parsed = _parse_single_box(box, page_text, page_num)
            if parsed:
                boxes.append(parsed)
    return boxes

def _resolve_box_offsets(
    markdown_text: str,
    header_boxes: list[dict],
) -> list[tuple[int, str]]:
    offsets: list[tuple[int, str]] = []
    for box in header_boxes:
        title = box["text"]
        search_start = 0 if not offsets else offsets[-1][0]
        idx = markdown_text.find(title, search_start)
        if idx < 0:
            idx = markdown_text.find(title)
        if idx >= 0:
            offsets.append((idx, title))
    offsets.sort(key=lambda x: x[0])
    return offsets

def _build_sections_from_offsets(
    markdown_text: str,
    offsets: list[tuple[int, str]],
) -> list[Section]:
    sections: list[Section] = []
    for i, (offset, title) in enumerate(offsets):
        start = offset + len(title)
        end = offsets[i + 1][0] if i + 1 < len(offsets) else len(markdown_text)
        content = markdown_text[start:end].strip()
        if content:
            sections.append(Section(title=title, content=content, level=1, order=i))
    return sections

def _sections_from_boxes(
    markdown_text: str,
    header_boxes: list[dict],
) -> list[Section]:
    if len(header_boxes) < 2:
        return []
    offsets = _resolve_box_offsets(markdown_text, header_boxes)
    if len(offsets) < 2:
        return []
    return _build_sections_from_offsets(markdown_text, offsets)

def _build_section(match: Match, idx: int, headings: list[Match], markdown_text: str) -> Section | None:
    title = (
        match.group(2).strip()
        if match.lastindex and match.lastindex >= 2
        else match.group(1).strip()
    )

    first_group = match.group(1)
    level = len(first_group) if first_group.startswith("#") else 1

    start = match.end()
    end = headings[idx + 1].start() if idx + 1 < len(headings) else len(markdown_text)
    content = markdown_text[start:end].strip()

    return Section(title=title, content=content, level=level, order=idx) if content else None

def _create_sections_from_headings(
    markdown_text: str, headings: list[Match]
) -> list[Section]:
    sections = []
    for idx, match in enumerate(headings):
        section = _build_section(match, idx, headings, markdown_text)
        if section:
            sections.append(section)
    return sections

def _create_default_section(markdown_text: str) -> list[Section]:
    return [Section(title="Full Document", content=markdown_text.strip(), order=0)]

def parse_sections(markdown_text: str, pages: list | None = None) -> list[Section]:
    if pages:
        header_boxes = _collect_header_boxes(pages)
        if header_boxes:
            box_sections = _sections_from_boxes(markdown_text, header_boxes)
            if box_sections:
                logger.info(
                    f"Parsed {len(box_sections)} sections via layout page_boxes"
                )
                return box_sections

    headings = _find_headings(markdown_text)
    sections = (
        _create_default_section(markdown_text)
        if not headings
        else _create_sections_from_headings(markdown_text, headings)
    )

    logger.info(f"Parsed {len(sections)} sections via regex fallback")
    return sections

