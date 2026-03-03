
from __future__ import annotations

import re
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

_CITE_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9_\-]")


def _extract_last_name(authors: str) -> str:
    """Extract the last name from the first author in authors string."""
    if not authors:
        return ""

    first_author = authors.split(";")[0].split("and")[0].strip()

    if "," in first_author:
        last_name = first_author.split(",")[0].strip()
    else:
        parts = first_author.split()
        last_name = parts[-1] if parts else ""

    return last_name


def _build_key_from_authors(authors: str, year_str: str) -> str | None:
    """Build cite key from authors. Returns None if unsuccessful."""
    last_name = _extract_last_name(authors)
    if not last_name:
        return None

    key = _CITE_KEY_UNSAFE.sub("", last_name) + year_str
    return key[:30] if key and key != year_str else None


def _build_key_from_title(title: str, year_str: str) -> str | None:
    """Build cite key from title. Returns None if unsuccessful."""
    if not title:
        return None

    words = re.sub(r"[^A-Za-z0-9 ]", "", title).split()
    key = "".join(w.capitalize() for w in words[:3]) + year_str
    return key[:30] if key != year_str else None


def _build_cite_key(paper: dict) -> str:
    authors: str = paper.get("authors") or ""
    year: int | None = paper.get("year")
    year_str = str(year) if year else "XXXX"

    key = _build_key_from_authors(authors, year_str)
    if key:
        return key

    title: str = paper.get("title") or ""
    key = _build_key_from_title(title, year_str)
    if key:
        return key

    return f"TraceLit_{str(paper.get('id', 'unknown'))[:8]}"


def _escape_bibtex(value: str) -> str:
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
    _field("note", paper.get("filename"))

    lines.append("}")
    return "\n".join(lines)


def export_papers_to_bibtex(papers: list[dict], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_keys: set[str] = set()
    entries: list[str] = []

    for paper in papers:
        key = _build_cite_key(paper)

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

