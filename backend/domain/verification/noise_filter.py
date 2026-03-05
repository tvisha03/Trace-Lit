import re
import unicodedata

_MIN_SOURCE_SENTENCE_WORDS = 4

_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

_TABLE_HEADER_RE = re.compile(r"^Table\s+\d+\s*:", re.IGNORECASE)
_FIGURE_HEADER_RE = re.compile(r"^Figure\s+\d+\s*:|^Fig\.\s+\d+\s*:", re.IGNORECASE)
_EQUATION_HEADER_RE = re.compile(
    r"^Eq(?:uation)?\s+\d+\s*:|^Formula\s+\d+\s*:", re.IGNORECASE,
)
_STRUCTURAL_LABEL_RE = re.compile(
    r"^(?:Stack|Goal|State|Input|Output)\s+\d*\s*:", re.IGNORECASE,
)

_PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s+\d+|p\.\s*\d+|-\s*\d+\s*-|\d{1,4})$", re.IGNORECASE,
)

_SECTION_HEADER_RE = re.compile(
    r"^(?:\d+\.[\d.]*\s+[A-Z]|[A-Z]\.[\d.]*\s+[A-Z]|[IVX]+\.\s+[A-Z])",
)

_URL_RE = re.compile(r"^https?://\S+$|^www\.\S+$|^ftp://\S+$", re.IGNORECASE)
_DOI_RE = re.compile(r"^(?:doi:\s*10\.\S+|https?://doi\.org/\S+)$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

_DATE_ONLY_RE = re.compile(
    r"^(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r"|Accessed:\s*.+)$",
    re.IGNORECASE,
)

_COPYRIGHT_RE = re.compile(
    r"(?:\u00a9|copyright|all rights reserved|licensed under|creative commons"
    r"|permission is granted|open access)",
    re.IGNORECASE,
)

_LATEX_ARTIFACT_RE = re.compile(
    r"\\(?:begin|end|textbf|textit|cite|ref|label|section|subsection"
    r"|caption|centering|includegraphics|usepackage)\s*\{",
)

_SEPARATOR_RE = re.compile(r"^[-=_*~]{3,}\s*$")

_REFERENCE_ENTRY_RE = re.compile(
    r"^(?:\[\d+\]\s*[A-Z]|(?:References|Bibliography|Works Cited)\s*$)",
    re.IGNORECASE,
)

_BOILERPLATE_RE = re.compile(
    r"^(?:Preprint|Submitted to|Accepted:|Published:|Received:|Revised:"
    r"|Under review|Draft|Proceedings of|Conference on"
    r"|arXiv:\d|Available at|Correspondence:|Keywords:)\s*",
    re.IGNORECASE,
)

_FOOTNOTE_MARKER_RE = re.compile(r"^[\d†‡*§¶]+\.?\s*$")

_BULLET_ONLY_RE = re.compile(r"^[\s•◦▪■○►◆★✦✓✗❑●⬤\-–—·]+$")

_BRACKET_ARTIFACT_RE = re.compile(
    r"^[\s\[\](){}]*$"
    r"|^\[\s*\?\s*\]$"
    r"|^\(\s*(?:see\s*)?\)$",
    re.IGNORECASE,
)

_CITATION_CLUSTER_RE = re.compile(r"^(?:\[[\d,;\s–-]+\])+\.?\s*$")

_WATERMARK_RE = re.compile(
    r"^(?:DRAFT|PREPRINT|CONFIDENTIAL|DO NOT DISTRIBUTE|"
    r"UNDER REVIEW|EMBARGOED?|SAMPLE|PROOF|UNCORRECTED)\s*$",
    re.IGNORECASE,
)

_ISSN_ISBN_RE = re.compile(r"^(?:e?ISSN|ISBN)[\s:]*[\dXx\-]+", re.IGNORECASE)

_VOLUME_ISSUE_RE = re.compile(
    r"^(?:Vol(?:ume)?\.?\s+\d|Issue\s+\d|No\.\s*\d|pp\.?\s*\d)",
    re.IGNORECASE,
)

_AFFILIATION_RE = re.compile(
    r"(?:University|Department|Institute|Laboratory|Lab\b|School of|"
    r"Faculty of|Center for|Centre for|College of|Hospital|"
    r"Research Group|Division of)",
    re.IGNORECASE,
)

_FUNDING_ACK_RE = re.compile(
    r"^(?:This (?:work|research|study|project) (?:was|is) "
    r"(?:supported|funded|sponsored|financed)|"
    r"(?:Supported|Funded|Sponsored|Financed) (?:by|in part)|"
    r"(?:Grant|Funding|Financial support|Acknowledgment)s?\s*(?::|from|by)|"
    r"The authors? (?:acknowledge|thank|would like to thank|gratefully))",
    re.IGNORECASE,
)

_JOURNAL_HEADER_RE = re.compile(
    r"^(?:Journal of|Proceedings of|Transactions on|"
    r"IEEE\s|ACM\s|Springer|Elsevier|Wiley|Nature\s|Science\s|"
    r"PLOS\s|Frontiers in|Annals of|"
    r"International (?:Journal|Conference)|Annual (?:Meeting|Conference))",
    re.IGNORECASE,
)

_INVISIBLE_CHARS_RE = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2060]",
)

_HYPHEN_BREAK_RE = re.compile(r"(\w)- (\w)")

def clean_source_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_CHARS_RE.sub("", text)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r" {2,}", " ", text)
    return text.strip()

def is_noise_source(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True

    if _is_too_short_or_structural(stripped):
        return True
    if _is_structural_noise(stripped):
        return True
    if _is_standalone_identifier(stripped):
        return True
    if _is_content_noise(stripped):
        return True
    if _is_artifact_or_metadata(stripped):
        return True

    return not _has_meaningful_content_after_images(stripped)

def _is_too_short_or_structural(text: str) -> bool:
    return (
        len(text.split()) < _MIN_SOURCE_SENTENCE_WORDS
        or text.startswith("|")
        or _is_metadata_header(text)
    )

def _is_structural_noise(text: str) -> bool:
    if _FOOTNOTE_MARKER_RE.match(text) or _SEPARATOR_RE.match(text):
        return True
    if _PAGE_NUMBER_RE.match(text):
        return True
    return bool(_SECTION_HEADER_RE.match(text) and len(text.split()) < 8)

def _is_standalone_identifier(text: str) -> bool:
    return bool(
        _URL_RE.match(text)
        or _DOI_RE.match(text)
        or _EMAIL_RE.match(text)
        or _DATE_ONLY_RE.match(text)
    )

def _is_content_noise(text: str) -> bool:
    return bool(
        _is_reference_entry(text)
        or _is_boilerplate(text)
        or _LATEX_ARTIFACT_RE.search(text)
        or _is_mostly_numeric(text)
    )

def _is_artifact_or_metadata(text: str) -> bool:
    return (
        _is_formatting_artifact(text)
        or _is_publication_metadata(text)
        or _has_excessive_special_chars(text)
    )

def _is_metadata_header(text: str) -> bool:
    return bool(
        _TABLE_HEADER_RE.match(text)
        or _FIGURE_HEADER_RE.match(text)
        or _EQUATION_HEADER_RE.match(text)
        or _STRUCTURAL_LABEL_RE.match(text)
    )

def _has_meaningful_content_after_images(text: str) -> bool:
    without_images = _IMG_MD_RE.sub("", text).strip()
    return len(without_images.split()) >= _MIN_SOURCE_SENTENCE_WORDS

def _is_mostly_numeric(text: str) -> bool:
    if not text:
        return True
    alpha_count = sum(1 for c in text if c.isalpha())
    return alpha_count / len(text) < 0.30

def _has_excessive_special_chars(text: str) -> bool:
    if len(text) < 10:
        return False
    special = sum(1 for c in text if not c.isalnum() and not c.isspace())
    return special / len(text) > 0.40

def _is_reference_entry(text: str) -> bool:
    return bool(
        _REFERENCE_ENTRY_RE.match(text)
        or text.startswith(("- [", "["))
        and any(c.isdigit() for c in text[:5])
    )

def _is_boilerplate(text: str) -> bool:
    return bool(
        _COPYRIGHT_RE.search(text)
        or _BOILERPLATE_RE.match(text)
    )

def _is_formatting_artifact(text: str) -> bool:
    return bool(
        _BULLET_ONLY_RE.match(text)
        or _BRACKET_ARTIFACT_RE.match(text)
        or _CITATION_CLUSTER_RE.match(text)
        or _WATERMARK_RE.match(text)
    )

def _is_publication_metadata(text: str) -> bool:
    if _ISSN_ISBN_RE.match(text) or _VOLUME_ISSUE_RE.match(text):
        return True
    if _FUNDING_ACK_RE.match(text):
        return True
    word_count = len(text.split())
    if word_count < 15 and _JOURNAL_HEADER_RE.match(text):
        return True
    if word_count < 15 and _AFFILIATION_RE.search(text):
        return True
    return False
