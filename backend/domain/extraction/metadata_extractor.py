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


_SKIP_HEADINGS = {
    "abstract", "introduction", "references", "contents",
    "related work", "related works", "background", "conclusion",
    "conclusions", "acknowledgements", "acknowledgments", "appendix",
    "bibliography", "methods", "methodology", "discussion",
}


def _is_valid_title_candidate(candidate: str) -> bool:
    if len(candidate) < 5 or len(candidate) > 300:
        return False
    stripped_num = re.sub(r"^[\d.IVXivx]+\s+", "", candidate).strip()
    if stripped_num.lower() in _SKIP_HEADINGS:
        return False
    if candidate.lower() in _SKIP_HEADINGS:
        return False
    if re.match(r"^[\d\.\s]+$", candidate):
        return False
    if _is_template_placeholder(candidate):
        return False
    return True


def _parse_title_box(box: dict, page_text: str) -> str | None:
    if not isinstance(box, dict) or box.get("class") not in ("title", "section-header"):
        return None
    pos = box.get("pos")
    if not pos or len(pos) < 2:
        return None
    raw = page_text[pos[0]:pos[1]].strip()
    raw = re.sub(r"^#+\s*", "", raw).strip("*").strip()
    return raw if _is_valid_title_candidate(raw) else None


def _find_title_box(page_boxes: list, page_text: str) -> str | None:
    for box in page_boxes:
        if isinstance(box, dict) and box.get("class") == "title":
            title = _parse_title_box(box, page_text)
            if title:
                return title
    return None


def _find_section_header_title(page_boxes: list, page_text: str) -> str | None:
    for box in page_boxes:
        if isinstance(box, dict) and box.get("class") == "section-header":
            title = _parse_title_box(box, page_text)
            if title:
                return title
    return None


def _find_first_text_title(page_boxes: list, page_text: str) -> str | None:
    if not page_boxes:
        return None
    first_box = page_boxes[0]
    if not isinstance(first_box, dict) or first_box.get("class") != "text":
        return None
    pos = first_box.get("pos", ())
    if len(pos) < 2 or pos[0] != 0:
        return None
    raw = re.sub(r"^#+\s*", "", page_text[pos[0]:pos[1]].strip()).strip("*").strip()
    return raw if _is_valid_title_candidate(raw) and len(raw) > 10 else None


def _extract_title_from_boxes(pages: list | None) -> str | None:
    if not pages:
        return None
    for page in pages[:2]:
        boxes = getattr(page, "page_boxes", None) or []
        text = getattr(page, "text", "")
        title = _find_title_box(boxes, text)
        if title:
            return title
    first_page = pages[0]
    boxes = getattr(first_page, "page_boxes", None) or []
    text = getattr(first_page, "text", "")
    return (
        _find_section_header_title(boxes, text)
        or _find_first_text_title(boxes, text)
    )


def _extract_title_from_text(head: str) -> str | None:
    heading = re.search(r"^#{1,2}\s+(.{5,200})$", head, re.MULTILINE)
    if heading:
        candidate = heading.group(1).strip().strip("*").strip()
        if _is_valid_title_candidate(candidate):
            return candidate

    bold_title = re.search(r"^\*{2}(.{5,200})\*{2}\s*$", head, re.MULTILINE)
    if bold_title and _is_valid_title_candidate(bold_title.group(1).strip()):
        return bold_title.group(1).strip()

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
    authors = re.sub(r"[,;\s]+$", "", authors)
    return authors if len(authors) > 3 else None


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
    if _is_pure_affiliation(line):
        return False
    name_matches = re.findall(r"[A-Z][a-z]+\s+[A-Z]", line)
    if not name_matches:
        return False
    has_separator = "," in line or " and " in line.lower() or ";" in line
    return has_separator or len(name_matches) >= 1


def _clean_author_line(line: str) -> str:
    cleaned = re.sub(r"\[.*?\]", "", line)
    cleaned = re.sub(r"[_*]", "", cleaned)
    cleaned = re.sub(r"\d+", "", cleaned)
    cleaned = re.sub(r"[†‡§¶∗◦·•]", "", cleaned)
    cleaned = _EMAIL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\{.*?\}", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"[,;\s]+$", "", cleaned)
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
    result = re.sub(r"[,;\s]+$", "", result)
    return result if len(result) > 3 else None


_NAME_PATTERN = re.compile(
    r"(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]{1,7})?)"
)


def _extract_bold_names(text: str) -> list[str]:
    bold_matches = re.findall(r"\*\*(.+?)\*\*", text)
    if not bold_matches:
        return []
    names: list[str] = []
    for candidate in bold_matches:
        candidate = re.sub(r"[\d†‡§¶∗◦·•]", "", candidate).strip()
        candidate = _EMAIL_PATTERN.sub("", candidate).strip()
        if 3 < len(candidate) < 100:
            m = _NAME_PATTERN.search(candidate)
            if m:
                names.append(m.group(1).strip())
    return names


def _clean_box_text_for_names(text: str) -> str:
    cleaned = re.sub(r"^#+\s*", "", text).strip()
    cleaned = re.sub(r"[_*]", "", cleaned).strip()
    cleaned = _EMAIL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    return re.sub(r"[\d†‡§¶∗◦·•]", "", cleaned)


def _extract_names_from_segments(cleaned: str) -> list[str]:
    segments = re.split(r"[,;]|\band\b", cleaned)
    names: list[str] = []
    for seg in segments:
        seg = re.sub(r"\s{2,}", " ", seg).strip()
        if seg and len(seg) >= 3:
            m = _NAME_PATTERN.search(seg)
            if m:
                names.append(m.group(1).strip())
    return [n for n in names if 3 < len(n) < 80]


def _extract_names_from_box_text(text: str) -> list[str]:
    bold_names = _extract_bold_names(text)
    if bold_names:
        return bold_names
    cleaned = _clean_box_text_for_names(text)
    if len(cleaned) < 3 or len(cleaned) > 500:
        return []
    if _AFFILIATION_MARKERS.search(cleaned):
        return []
    return _extract_names_from_segments(cleaned)


def _find_author_boundaries(
    page_boxes: list, page_text: str, title_lower: str
) -> tuple[int, int]:
    title_end = 0
    abstract_start = len(page_text)
    for box in page_boxes:
        pos = box.get("pos", (0, 0))
        raw = page_text[pos[0]:pos[1]].strip()
        cleaned = re.sub(r"^#+\s*", "", raw).strip("*").strip()
        if title_lower and cleaned.lower().startswith(title_lower):
            title_end = max(title_end, pos[1])
            continue
        if re.search(r"\babstract\b", cleaned, re.IGNORECASE):
            abstract_start = pos[0]
            break
    return title_end, abstract_start


def _collect_names_between(
    page_boxes: list, page_text: str, start: int, end: int
) -> list[str]:
    names: list[str] = []
    for box in page_boxes:
        pos = box.get("pos", (0, 0))
        if pos[0] < start or pos[0] >= end:
            continue
        raw = page_text[pos[0]:pos[1]].strip()
        for name in _extract_names_from_box_text(raw):
            if name not in names:
                names.append(name)
    return names


def _get_first_page_data(pages: list | None) -> tuple[list, str] | None:
    if not pages or not pages[0]:
        return None
    page = pages[0]
    boxes = getattr(page, "page_boxes", None) or []
    if not boxes:
        return None
    return boxes, getattr(page, "text", "")


def _extract_authors_from_boxes(pages: list | None, title: str | None) -> str | None:
    page_data = _get_first_page_data(pages)
    if not page_data:
        return None
    boxes, text = page_data
    title_lower = (title or "").lower()[:40]
    title_end, abstract_start = _find_author_boundaries(boxes, text, title_lower)
    if title_end == 0 or title_end >= abstract_start:
        return None
    names = _collect_names_between(boxes, text, title_end, abstract_start)
    if not names:
        return None
    return re.sub(r"[,;\s]+$", "", "; ".join(names)) or None


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
        authors = _extract_authors_from_boxes(pages, title)
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

