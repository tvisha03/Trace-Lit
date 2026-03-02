import re
from dataclasses import dataclass
from re import Match

from shared.logger import get_logger

logger = get_logger(__name__)

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_NUMBERED_HEADING = re.compile(
    r"^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s:,\-–—]+)$", re.MULTILINE
)

@dataclass
class Section:
    title: str
    content: str
    level: int = 1
    page_start: int | None = None
    order: int = 0

def _find_headings(markdown_text: str) -> list[Match]:
    headings = list(_MD_HEADING.finditer(markdown_text))
    return headings or list(_NUMBERED_HEADING.finditer(markdown_text))

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

def parse_sections(markdown_text: str) -> list[Section]:
    headings = _find_headings(markdown_text)
    sections = (
        _create_default_section(markdown_text)
        if not headings
        else _create_sections_from_headings(markdown_text, headings)
    )

    logger.info(f"Parsed {len(sections)} sections")
    return sections
