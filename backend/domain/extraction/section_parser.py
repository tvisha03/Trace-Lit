"""
Section parser — splits raw Markdown into structured sections.
Detects headings via Markdown syntax, font-size heuristics, and numbering patterns.
"""

import re
from dataclasses import dataclass, field

from shared.logger import get_logger

logger = get_logger(__name__)

# Patterns for academic section headings
_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_NUMBERED_HEADING = re.compile(
    r"^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s:,\-–—]+)$", re.MULTILINE
)


@dataclass
class Section:
    """A logical section extracted from a paper."""
    title: str
    content: str
    level: int = 1  # heading depth (1 = top-level)
    page_start: int | None = None
    order: int = 0


def parse_sections(markdown_text: str) -> list[Section]:
    """
    Split Markdown text into ordered sections.

    Strategy:
    1. Find all ``## Heading`` style markers.
    2. Fall back to numbered heading detection (``1. Introduction``).
    3. If no headings found, treat the whole document as one section.
    """
    sections: list[Section] = []

    # Try Markdown headings first
    headings = list(_MD_HEADING.finditer(markdown_text))

    if not headings:
        # Fallback: numbered headings
        headings = list(_NUMBERED_HEADING.finditer(markdown_text))

    if not headings:
        # No structure detected — wrap everything in a single section
        sections.append(Section(title="Full Document", content=markdown_text.strip(), order=0))
        return sections

    for idx, match in enumerate(headings):
        title = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
        level = len(match.group(1)) if match.group(1).startswith("#") else 1

        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(markdown_text)
        content = markdown_text[start:end].strip()

        if content:
            sections.append(Section(
                title=title.strip(),
                content=content,
                level=level,
                order=idx,
            ))

    logger.info(f"Parsed {len(sections)} sections")
    return sections
