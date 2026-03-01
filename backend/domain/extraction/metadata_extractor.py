"""
Metadata extractor — pulls title, authors, year, and abstract from PDF text.
Uses regex heuristics on the first page of extracted Markdown.
"""

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


def extract_metadata(markdown_text: str) -> PaperMetadata:
    """
    Best-effort metadata extraction from the first ~3000 characters.
    Falls back to None for any field it cannot detect.
    """
    head = markdown_text[:3000]
    meta = PaperMetadata()

    # Title: first Markdown heading or first non-empty line
    title_match = re.search(r"^#{1,2}\s+(.+)$", head, re.MULTILINE)
    if title_match:
        meta.title = title_match.group(1).strip()
    else:
        first_line = head.strip().split("\n")[0].strip()
        if len(first_line) > 5:
            meta.title = first_line

    # Year: 4-digit number in range 1900–2099
    year_match = re.search(r"\b(19|20)\d{2}\b", head)
    if year_match:
        meta.year = int(year_match.group())

    # Abstract: text after "Abstract" heading or keyword
    abstract_match = re.search(
        r"(?:^#{1,3}\s*Abstract|^\*{0,2}Abstract\*{0,2})\s*\n+([\s\S]{50,1500}?)(?=\n#{1,3}\s|\n\*{2}|\n\d+[\.\s])",
        head,
        re.MULTILINE | re.IGNORECASE,
    )
    if abstract_match:
        meta.abstract = abstract_match.group(1).strip()

    # Authors: line(s) immediately after title, containing commas or "and"
    if meta.title:
        after_title = head.split(meta.title, 1)[-1].strip()
        lines = after_title.split("\n")
        for line in lines[:5]:
            clean = line.strip().strip("*").strip()
            if clean and ("," in clean or " and " in clean.lower()) and len(clean) < 500:
                meta.authors = clean
                break

    logger.info(f"Extracted metadata: title={meta.title!r}, year={meta.year}")
    return meta
