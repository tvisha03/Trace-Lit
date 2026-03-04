"""Text-cleaning helpers shared across all export formats.

These functions strip raw markdown artefacts and replace Unicode characters
that cause problems in non-Unicode font renderers (fpdf2 Helvetica).
"""

import re

# ---------------------------------------------------------------------------
# Markdown → plain-text cleanup
# ---------------------------------------------------------------------------

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
# Internal citation tags like [P12], [T3], [P12-S5] used by TraceLit
_CITATION_TAG = re.compile(r"\[(?:P|T)\d+(?:-S\d+)?\]")


def strip_markdown(text: str) -> str:
    """Convert markdown to clean plain text for exports."""
    text = _MD_IMAGE.sub("", text)
    text = _MD_CODE_BLOCK.sub("", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_BOLD_ITALIC.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    text = _MD_HR.sub("", text)
    text = _MD_LIST_MARKER.sub("  ", text)
    text = _MD_NUMBERED_LIST.sub("  ", text)
    text = _CITATION_TAG.sub("", text)
    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Unicode → Latin-1 safe replacements  (for fpdf2 built-in fonts)
# ---------------------------------------------------------------------------

_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u2014": "--",      # em dash  —
    "\u2013": "-",       # en dash  –
    "\u2018": "'",       # left single quote  '
    "\u2019": "'",       # right single quote  '
    "\u201c": '"',       # left double quote  "
    "\u201d": '"',       # right double quote  "
    "\u2026": "...",     # ellipsis  …
    "\u2022": "*",       # bullet  •
    "\u00d7": "x",       # multiplication  ×
    "\u2264": "<=",      # less-than-or-equal  ≤
    "\u2265": ">=",      # greater-than-or-equal  ≥
    "\u2260": "!=",      # not-equal  ≠
    "\u2192": "->",      # right arrow  →
    "\u2190": "<-",      # left arrow  ←
    "\u00b1": "+/-",     # plus-minus  ±
    "\u00b0": "deg",     # degree  °
    "\u03b1": "alpha",   # α
    "\u03b2": "beta",    # β
    "\u03b3": "gamma",   # γ
    "\u03b4": "delta",   # δ
    "\u03c3": "sigma",   # σ
    "\u03bc": "mu",      # μ
    "\u2032": "'",       # prime  ′
    "\u2033": "''",      # double prime  ″
}

_UNICODE_RE = re.compile(
    "|".join(re.escape(k) for k in _UNICODE_REPLACEMENTS)
)


def sanitize_for_pdf(text: str) -> str:
    """Replace Unicode characters unsupported by fpdf2 Helvetica.

    Any remaining non-Latin-1 characters are silently dropped so the PDF
    renderer never raises a glyph-not-found error.
    """
    text = _UNICODE_RE.sub(lambda m: _UNICODE_REPLACEMENTS[m.group()], text)
    # Drop any remaining non-Latin-1 characters
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def clean_for_export(text: str) -> str:
    """Full pipeline: strip markdown then sanitize for PDF-safe output."""
    return sanitize_for_pdf(strip_markdown(text))
