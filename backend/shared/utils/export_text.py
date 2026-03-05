import re

_MD_BOLD_ITALIC = re.compile(r"\*{1,3}(.+?)\*{1,3}")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_CODE_BLOCK = re.compile(r"```[a-z]*\n?|```")
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_BLOCKQUOTE = re.compile(r"^>\s?", re.MULTILINE)
_MD_HR = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_MD_LIST_MARKER = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
_MD_NUMBERED_LIST = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
_CITATION_TAG = re.compile(r"\[(?:[PTFE]\d+)(?:-S\d+)?\]")
_PARA_ID_TAG = re.compile(r"\[[a-f0-9]{8}_[PTFE]\d+\]")

def strip_markdown(text: str) -> str:
    text = _MD_IMAGE.sub("", text)
    text = _MD_CODE_BLOCK.sub("", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_BOLD_ITALIC.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    text = _MD_HR.sub("", text)
    text = _MD_LIST_MARKER.sub("  - ", text)
    text = _MD_NUMBERED_LIST.sub("  ", text)
    text = _PARA_ID_TAG.sub("", text)
    text = _CITATION_TAG.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def format_structured_text(text: str) -> str:
    text = re.sub(r"^#{1,2}\s+(.+)$", lambda m: m.group(1).upper(), text, flags=re.MULTILINE)
    text = re.sub(r"^#{3,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
    text = _MD_BOLD_ITALIC.sub(r"\1", text)
    text = _MD_IMAGE.sub("", text)
    text = _MD_CODE_BLOCK.sub("", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _PARA_ID_TAG.sub("", text)
    text = _CITATION_TAG.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u2014": "--",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u2022": "*",
    "\u00d7": "x",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2260": "!=",
    "\u2192": "->",
    "\u2190": "<-",
    "\u00b1": "+/-",
    "\u00b0": "deg",
    "\u03b1": "alpha",
    "\u03b2": "beta",
    "\u03b3": "gamma",
    "\u03b4": "delta",
    "\u03c3": "sigma",
    "\u03bc": "mu",
    "\u2032": "'",
    "\u2033": "''",
}

_UNICODE_RE = re.compile(
    "|".join(re.escape(k) for k in _UNICODE_REPLACEMENTS)
)

def sanitize_for_pdf(text: str) -> str:
    text = _UNICODE_RE.sub(lambda m: _UNICODE_REPLACEMENTS[m.group()], text)
    return text.encode("latin-1", errors="ignore").decode("latin-1")

def clean_for_export(text: str) -> str:
    return sanitize_for_pdf(strip_markdown(text))
