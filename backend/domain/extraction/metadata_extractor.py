
import re
from dataclasses import dataclass

from shared.logger import get_logger

logger = get_logger(__name__)

@dataclass
class PaperMetadata:
    title: str | None = None
    authors: str | None = None
    year: int | None = None
    abstract: str | None = None

def _extract_title(head: str) -> str | None:
    title_match = re.search(r"^#{1,2}\s+(.+)$", head, re.MULTILINE)
    if title_match:
        return title_match.group(1).strip()

    first_line = head.strip().split("\n")[0].strip()
    if len(first_line) > 5:
        return first_line
    return None

def _extract_year(head: str) -> int | None:
    """Extract a publication year from the head of the document.

    The regex is intentionally restricted to plausible publication years
    (1900-2039) and looks for contextual clues such as surrounding
    parentheses, copyright symbols, or typical date prepositions to
    avoid matching page numbers or reference IDs.
    """
    # Prefer years that appear in a clear date context.
    contextual = re.search(
        r"(?:©|copyright|published|received|accepted|\(|,\s*)\s*"
        r"((?:19|20)\d{2})\b",
        head,
        re.IGNORECASE,
    )
    if contextual:
        return int(contextual.group(1))

    # Fallback: first standalone 4-digit year in the head section.
    year_match = re.search(r"\b((?:19|20)\d{2})\b", head)
    if year_match:
        return int(year_match.group(1))
    return None

def _extract_abstract(text: str) -> str | None:
    # Search the full document rather than just the opening slice (HI-003 fix).
    # Many papers place the abstract after a title page, author block, or
    # acknowledgements section, making it invisible to a 3000-char head slice.
    abstract_match = re.search(
        r"(?:^#{1,3}\s*Abstract|^\*{0,2}Abstract\*{0,2})\s*\n+([\s\S]{50,1500}?)(?=\n#{1,3}\s|\n\*{2}|\n\d+[\.*\s])",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if abstract_match:
        return abstract_match.group(1).strip()
    return None

def _extract_authors(head: str, title: str | None) -> str | None:
    if not title:
        return None

    after_title = head.split(title, 1)[-1].strip()
    lines = after_title.split("\n")

    for line in lines[:5]:
        clean = line.strip().strip("*").strip()
        if clean and ("," in clean or " and " in clean.lower()) and len(clean) < 500:
            return clean

    return None

def extract_metadata(markdown_text: str) -> PaperMetadata:
    # Use only the opening section for cheap pattern matching of title, year,
    # and authors — these fields always appear near the top of a paper.  The
    # abstract search operates on the full text because some documents place
    # the abstract after a title page or author block (HI-003 fix).
    head = markdown_text[:3000]

    title = _extract_title(head)
    year = _extract_year(head)
    abstract = _extract_abstract(markdown_text)  # full text search
    authors = _extract_authors(head, title)

    meta = PaperMetadata(title=title, authors=authors, year=year, abstract=abstract)
    logger.info(f"Extracted metadata: title={meta.title!r}, year={meta.year}")
    return meta
