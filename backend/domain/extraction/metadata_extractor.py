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


_TEMPLATE_TITLE_PATTERNS = [
    re.compile(r"paper\s+title", re.IGNORECASE),
    re.compile(r"use\s+style", re.IGNORECASE),
    re.compile(r"enter\s+(?:the\s+)?title", re.IGNORECASE),
    re.compile(r"your\s+title\s+here", re.IGNORECASE),
    re.compile(r"insert\s+title", re.IGNORECASE),
    re.compile(r"title\s+of\s+(?:the\s+)?(?:paper|manuscript|article)", re.IGNORECASE),
    re.compile(r"manuscript\s+title", re.IGNORECASE),
    re.compile(r"^untitled", re.IGNORECASE),
    re.compile(r"sample\s+(?:paper|article|manuscript)", re.IGNORECASE),
    re.compile(r"template", re.IGNORECASE),
]

_PUBLISHER_NAMES = {
    "ieee", "acm", "springer", "elsevier", "wiley", "nature", "science",
    "oxford university press", "cambridge university press", "taylor & francis",
    "mdpi", "frontiers", "plos", "arxiv", "biorxiv", "medrxiv",
    "microsoft word", "microsoft", "latex", "overleaf",
    "apple", "google", "meta", "openai",
}


def _clean_pdf_string(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("D:"):
        return None
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    return cleaned if len(cleaned) > 1 else None


def _is_template_placeholder(text: str) -> bool:
    return any(p.search(text) for p in _TEMPLATE_TITLE_PATTERNS)


def _extract_title_from_pdf_meta(pdf_meta: dict | None) -> str | None:
    if not pdf_meta:
        return None
    raw = pdf_meta.get("title", "")
    title = _clean_pdf_string(raw)
    if not title or len(title) <= 3:
        return None
    if _is_template_placeholder(title):
        return None
    return title


_SKIP_HEADINGS = {"abstract", "introduction", "references", "contents"}


def _is_valid_title_candidate(candidate: str) -> bool:
    if len(candidate) < 5 or len(candidate) > 300:
        return False
    if candidate.lower() in _SKIP_HEADINGS:
        return False
    if re.match(r"^[\d\.\s]+$", candidate):
        return False
    if _is_template_placeholder(candidate):
        return False
    return True


def _parse_title_box(box: dict, page_text: str) -> str | None:
    if not isinstance(box, dict) or box.get("class") != "title":
        return None
    pos = box.get("pos")
    if not pos or len(pos) < 2:
        return None
    raw = page_text[pos[0]:pos[1]].strip()
    raw = re.sub(r"^#+\s*", "", raw).strip("*").strip()
    return raw if _is_valid_title_candidate(raw) else None


def _extract_title_from_boxes(pages: list | None) -> str | None:
    if not pages:
        return None
    for page in pages[:2]:
        page_boxes = getattr(page, "page_boxes", None) or []
        page_text = getattr(page, "text", "")
        for box in page_boxes:
            title = _parse_title_box(box, page_text)
            if title:
                return title
    return None


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
    if not authors or len(authors) < 3:
        return None
    if authors.lower().strip() in _PUBLISHER_NAMES:
        return None
    if _is_template_placeholder(authors):
        return None
    return authors


_STOP_PREFIXES = ("abstract", "introduction", "#", "keyword", "index term")

_AFFILIATION_MARKERS = re.compile(
    r"university|institute|department|school|college|lab|center|centre|"
    r"faculty|hospital|inc\.|corp\.|ltd\.|@|\.edu|\.ac\.|\.org",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _is_pure_affiliation(line: str) -> bool:
    return bool(
        _AFFILIATION_MARKERS.search(line)
        and not re.search(r"[A-Z][a-z]+\s+[A-Z]", line)
    )


def _is_author_line(line: str) -> bool:
    if len(line) > 1000 or len(line) < 3:
        return False
    if _EMAIL_PATTERN.search(line) or _is_pure_affiliation(line):
        return False
    name_matches = re.findall(r"[A-Z][a-z]+\s+[A-Z]", line)
    if not name_matches:
        return False
    has_separator = "," in line or " and " in line.lower()
    return has_separator or len(name_matches) >= 2


def _clean_author_line(line: str) -> str:
    cleaned = re.sub(r"\[.*?\]", "", line)
    cleaned = re.sub(r"[_*]", "", cleaned)
    cleaned = re.sub(r"\d+", "", cleaned)
    cleaned = re.sub(r"[†‡§¶∗◦·•]", "", cleaned)
    cleaned = _EMAIL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\{.*?\}", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _should_stop_author_scan(line: str) -> bool:
    return not line or len(line) < 3 or line.lower().startswith(_STOP_PREFIXES)


def _get_text_after_title(head: str, title: str | None) -> str:
    if not title:
        return head
    idx = head.find(title)
    if idx < 0:
        return head
    return head[idx + len(title):].strip()


def _collect_author_lines(text: str) -> list[str]:
    author_lines: list[str] = []
    started = False
    for line in text.split("\n")[:20]:
        clean = line.strip().strip("*").strip()
        if _should_stop_author_scan(clean):
            if clean.lower().startswith(_STOP_PREFIXES):
                break
            if started:
                break
            continue
        if _is_author_line(clean):
            started = True
            author_lines.append(_clean_author_line(clean))
        elif started:
            break
    return author_lines


def _extract_authors_from_text(head: str, title: str | None) -> str | None:
    after = _get_text_after_title(head, title)
    author_lines = _collect_author_lines(after)
    if not author_lines:
        return None
    result = ", ".join(author_lines)
    return result if len(result) > 3 else None


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
        r"(?:©|copyright|published|received|accepted|submitted|\(|,\s*|"
        r"arxiv[:\s]*\d+\.\d+v?\d*\s*\[.*?\]\s*|"
        r"vol(?:ume)?\.?\s*\d+|no\.?\s*\d+|pp\.?\s*\d+|"
        r"doi[:\s]|issn[:\s]|isbn[:\s])"
        r"\s*((?:19|20)\d{2})\b",
        head,
        re.IGNORECASE,
    )
    if contextual:
        return int(contextual.group(1))

    date_pattern = re.search(
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
        r"[\s.,]+(?:\d{1,2}[\s.,]+)?((?:19|20)\d{2})",
        head,
        re.IGNORECASE,
    )
    if date_pattern:
        return int(date_pattern.group(1))

    year_match = re.search(r"\b((?:19|20)\d{2})\b", head)
    if year_match:
        return int(year_match.group(1))
    return None


def _extract_abstract_from_text(text: str) -> str | None:
    search_area = text[:10000]

    abstract_match = re.search(
        r"[_*]*\bAbstract\b[_*]*",
        search_area,
        re.IGNORECASE,
    )
    if not abstract_match:
        return None

    after = search_area[abstract_match.end():]
    after = re.sub(r"^[\s_*—\-:.]+", "", after)

    end_match = re.search(
        r"(?:"
        r"\n\s*#{1,3}\s"
        r"|\n\s*[_*]{0,4}(?:1[\s.]|I[\s.]|Introduction|Keywords|Index\s+Terms|CCS\s+Concepts)[_*]{0,4}"
        r"|\n\s*\*{2}\d+[.\s]*\*{2}"
        r"|\n\s*\*{2}(?:Introduction|Keywords|Background|Related|Methods?)\*{2}"
        r"|\n\s*\n\s*\n"
        r")",
        after,
        re.IGNORECASE,
    )

    end_pos = min(end_match.start() if end_match else len(after), 3000)
    abstract = after[:end_pos].strip()
    abstract = re.sub(r"\n+", " ", abstract)
    abstract = re.sub(r"\s{2,}", " ", abstract)

    if 30 < len(abstract) < 5000:
        return abstract
    return None


def extract_metadata(
    markdown_text: str,
    pdf_metadata: dict | None = None,
    pages: list | None = None,
) -> PaperMetadata:
    head = markdown_text[:5000]

    title = _extract_title_from_pdf_meta(pdf_metadata)
    if not title:
        title = _extract_title_from_boxes(pages)
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

