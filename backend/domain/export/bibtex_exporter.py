"""BibTeX export for uploaded academic papers.

Generates a standard .bib file from the metadata stored for each paper
in a session.  Entry type defaults to @article; callers can override by
passing ``entry_type`` in the paper dict.

References: https://www.bibtex.org/Format/
"""

from __future__ import annotations

import re
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

# Characters that are invalid in a BibTeX cite key.
_CITE_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9_\-]")


def _build_cite_key(paper: dict) -> str:
    """Derive a unique, collision-resistant BibTeX cite key.

    Strategy: LastnameYear where Lastname is the first author's last name
    (split on comma for "Last, First" format or space for "First Last").
    Falls back to a sanitised version of the title, then the paper ID.
    """
    authors: str = paper.get("authors") or ""
    year: int | None = paper.get("year")
    year_str = str(year) if year else "XXXX"

    if authors:
        # Handle both "First Last, First2 Last2" and "Last, First" formats.
        first_author = authors.split(";")[0].split("and")[0].strip()
        if "," in first_author:
            # "Last, First" — take the part before the comma.
            last_name = first_author.split(",")[0].strip()
        else:
            # "First Last" — take the last word.
            parts = first_author.split()
            last_name = parts[-1] if parts else ""

        key = _CITE_KEY_UNSAFE.sub("", last_name) + year_str
        if key and key != year_str:
            return key[:30]  # cap length for readability

    # Fall back to first three words of the title.
    title: str = paper.get("title") or ""
    if title:
        words = re.sub(r"[^A-Za-z0-9 ]", "", title).split()
        key = "".join(w.capitalize() for w in words[:3]) + year_str
        if key != year_str:
            return key[:30]

    # Final fallback: use the paper ID prefix.
    return f"TraceLit_{str(paper.get('id', 'unknown'))[:8]}"


def _escape_bibtex(value: str) -> str:
    """Minimally escape special BibTeX characters inside braces."""
    # The most common problematic chars in title/abstract text.
    return (
        value
        .replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("~", "\\textasciitilde{}")
        .replace("^", "\\textasciicircum{}")
    )


def _format_entry(paper: dict, cite_key: str) -> str:
    """Render a single BibTeX entry block for one paper."""
    entry_type = paper.get("entry_type", "article")
    lines: list[str] = [f"@{entry_type}{{{cite_key},"]

    def _field(name: str, value: str | int | None) -> None:
        if value:
            escaped = _escape_bibtex(str(value))
            lines.append(f"  {name} = {{{escaped}}},")

    _field("title", paper.get("title"))
    _field("author", paper.get("authors"))
    _field("year", paper.get("year"))
    _field("abstract", paper.get("abstract"))
    _field("note", paper.get("filename"))  # original filename for traceability

    lines.append("}")
    return "\n".join(lines)


def export_papers_to_bibtex(papers: list[dict], output_path: Path) -> Path:
    """Write a .bib file containing one entry per paper.

    Args:
        papers: List of paper metadata dicts.  Expected keys: ``id``,
            ``title``, ``authors``, ``year``, ``abstract``, ``filename``.
        output_path: Destination path for the generated .bib file.

    Returns:
        The resolved output path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_keys: set[str] = set()
    entries: list[str] = []

    for paper in papers:
        key = _build_cite_key(paper)

        # Guarantee uniqueness by appending a counter if the key collides.
        if key in seen_keys:
            counter = 2
            while f"{key}{counter}" in seen_keys:
                counter += 1
            key = f"{key}{counter}"
        seen_keys.add(key)

        entries.append(_format_entry(paper, key))
        logger.debug(f"BibTeX entry generated: {key}")

    bib_content = "\n\n".join(entries) + "\n"
    output_path.write_text(bib_content, encoding="utf-8")
    logger.info(f"BibTeX export written: {output_path} ({len(papers)} entries)")
    return output_path
