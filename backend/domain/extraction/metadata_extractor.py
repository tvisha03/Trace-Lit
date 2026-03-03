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


def _clean_pdf_string(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("D:"):
        return None
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    return cleaned if len(cleaned) > 1 else None


def _extract_title_from_pdf_meta(pdf_meta: dict | None) -> str | None:
    if not pdf_meta:
        return None
    raw = pdf_meta.get("title", "")
    title = _clean_pdf_string(raw)
    if title and len(title) > 3 and not title.lower().startswith("untitled"):
        return title
    return None


_SKIP_HEADINGS = {"abstract", "introduction", "references", "contents"}


def _is_valid_title_candidate(candidate: str) -> bool:
    if len(candidate) < 5 or len(candidate) > 300:
        return False
    if candidate.lower() in _SKIP_HEADINGS:
        return False
    if re.match(r"^[\d\.\s]+$", candidate):
        return False
    return True


def _extract_title_from_text(head: str) -> str | None:
    bold_title = re.search(r"^\*{2}(.{5,200})\*{2}\s*$", head, re.MULTILINE)
    if bold_title and _is_valid_title_candidate(bold_title.group(1).strip()):
        return bold_title.group(1).strip()

    heading = re.search(r"^#{1,2}\s+(.{5,200})$", head, re.MULTILINE)
    if heading:
        candidate = heading.group(1).strip().strip("*").strip()
        if _is_valid_title_candidate(candidate):
            return candidate

    for line in head.strip().split("\n")[:10]:
        stripped = line.strip().strip("*").strip("#").strip()
        if _is_valid_title_candidate(stripped) and len(stripped) > 10:
            return stripped
    return None


def _extract_authors_from_pdf_meta(pdf_meta: dict | None) -> str | None:
    if not pdf_meta:
        return None
    raw = pdf_meta.get("author", "")
    authors = _clean_pdf_string(raw)
    if authors and len(authors) > 2:
        return authors
    return None


_STOP_PREFIXES = ("abstract", "introduction", "#", "keyword")


def _is_author_line(line: str) -> bool:
    has_name_pattern = bool(re.search(r"[A-Z][a-z]+\s+[A-Z]", line))
    has_separator = "," in line or " and " in line.lower()
    return has_name_pattern and has_separator and len(line) < 1000


def _clean_author_line(line: str) -> str:
    cleaned = re.sub(r"\d+", "", line)
    cleaned = re.sub(r"[†‡§¶∗◦]", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _should_stop_author_scan(line: str) -> bool:
    return not line or len(line) < 3 or line.lower().startswith(_STOP_PREFIXES)


def _extract_authors_from_text(head: str, title: str | None) -> str | None:
    after = head
    if title:
        idx = head.find(title)
        if idx >= 0:
            after = head[idx + len(title):].strip()

    for line in after.split("\n")[:8]:
        clean = line.strip().strip("*").strip()
        if _should_stop_author_scan(clean):
            if clean.lower().startswith(_STOP_PREFIXES):
                break
            continue
        if not _is_author_line(clean):
            continue
        result = _clean_author_line(clean)
        if len(result) > 3:
            return result
    return None


def _extract_year_from_pdf_meta(pdf_meta: dict | None) -> int | None:
    if not pdf_meta:
        return None

    for key in ("creationDate", "modDate"):
        raw = pdf_meta.get(key, "")
        if not raw:
            continue
        match = re.search(r"D:(\d{4})", raw)
        if match:
            year = int(match.group(1))
            if 1900 <= year <= 2100:
                return year
        match = re.search(r"((?:19|20)\d{2})", raw)
        if match:
            year = int(match.group(1))
            if 1900 <= year <= 2100:
                return year
    return None


def _extract_year_from_text(head: str) -> int | None:
    contextual = re.search(
        r"(?:©|copyright|published|received|accepted|submitted|\(|,\s*|arxiv[:\s]*\d+\.\d+v?\d*\s*\[.*?\]\s*)"
        r"\s*((?:19|20)\d{2})\b",
        head,
        re.IGNORECASE,
    )
    if contextual:
        return int(contextual.group(1))

    date_pattern = re.search(
        r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
        r"[\s,]+(\d{1,2}[\s,]+)?((?:19|20)\d{2})",
        head,
        re.IGNORECASE,
    )
    if date_pattern:
        return int(date_pattern.group(2))

    year_match = re.search(r"\b((?:19|20)\d{2})\b", head)
    if year_match:
        return int(year_match.group(1))
    return None


def _extract_abstract_from_text(text: str) -> str | None:
    patterns = [
        re.compile(
            r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:\*{0,2})Abstract(?:\*{0,2})[.\s]*\n+([\s\S]{50,3000}?)(?=\n\s*(?:#{1,3}\s|(?:\*{2})?(?:1[\s.]|I[\s.]|Introduction|Keywords|Index\s+Terms)))",
            re.MULTILINE | re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\n)\s*(?:\*{0,2})Abstract(?:\*{0,2})[.\s:]*\n+([\s\S]{50,3000}?)(?=\n\s*\n\s*\n)",
            re.MULTILINE | re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\n)\s*(?:\*{0,2})Abstract(?:\*{0,2})[.\s:—-]*(.{50,3000}?)(?=\n\s*(?:#{1,3}\s|(?:\*{2})?(?:1[\s.]|I[\s.]|Introduction|Keywords)))",
            re.MULTILINE | re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text[:10000])
        if match:
            abstract = match.group(1).strip()
            abstract = re.sub(r"\n+", " ", abstract)
            abstract = re.sub(r"\s{2,}", " ", abstract)
            if 30 < len(abstract) < 5000:
                return abstract
    return None


def extract_metadata(
    markdown_text: str,
    pdf_metadata: dict | None = None,
) -> PaperMetadata:
    head = markdown_text[:5000]

    title = _extract_title_from_pdf_meta(pdf_metadata)
    if not title:
        title = _extract_title_from_text(head)

    authors = _extract_authors_from_pdf_meta(pdf_metadata)
    if not authors:
        authors = _extract_authors_from_text(head, title)

    year = _extract_year_from_pdf_meta(pdf_metadata)
    if not year:
        year = _extract_year_from_text(head)

    abstract = _extract_abstract_from_text(markdown_text)

    meta = PaperMetadata(title=title, authors=authors, year=year, abstract=abstract)
    logger.info(
        f"Extracted metadata: title={meta.title!r}, "
        f"authors={meta.authors!r:.80}, year={meta.year}, "
        f"abstract_len={len(meta.abstract) if meta.abstract else 0}"
    )
    return meta

