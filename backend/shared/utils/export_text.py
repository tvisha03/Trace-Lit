from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_-]*\n?|```")
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_BLOCKQUOTE = re.compile(r"^>\s?", re.MULTILINE)
_MD_HR = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_MD_LIST_MARKER = re.compile(r"^[\s]*[-*+]\s+")
_MD_NUMBERED_LIST = re.compile(r"^[\s]*(\d+)\.\s+")
_MD_TABLE_SEP_RE = re.compile(r"^\|?[\s:]*-{2,}[\s:]*(?:\|[\s:]*-{2,}[\s:]*)+\|?\s*$")
_PARA_ID_TAG = re.compile(r"\[[a-f0-9]{8}_[PTFE]\d+\]")
# Matches both old-style [P16] and new UUID-prefixed [abc12345_P16] citation tags.
_CITATION_TAG = re.compile(r"\[(?:[a-f0-9]{1,8}_)?[PTFE]\d+(?:-S\d+)?\]")
# Strips the AI-generated disclaimer note appended when citations cannot be verified.
_DISCLAIMER_RE = re.compile(r"\n\n---\n_?⚠️[^\n]*(?:\n[^\n]*)*?_?\s*$", re.DOTALL)
_INLINE_PATTERN = re.compile(
    r"(\*\*[^*\n]+\*\*|\*[^*\n]+\*|\\\$[^$\n]+\\\$|\$[^$\n]+\$|\\\([^\n]+?\\\)|\\\[[\s\S]+?\\\])"
)

_LATEX_TO_UNICODE: dict[str, str] = {
    r"\alpha": "alpha",
    r"\beta": "beta",
    r"\gamma": "gamma",
    r"\delta": "delta",
    r"\epsilon": "epsilon",
    r"\lambda": "lambda",
    r"\mu": "mu",
    r"\pi": "pi",
    r"\sigma": "sigma",
    r"\theta": "theta",
    r"\times": "x",
    r"\otimes": "⊗",
    r"\pm": "+/-",
    r"\leq": "<=",
    r"\geq": ">=",
    r"\neq": "!=",
    r"\rightarrow": "->",
    r"\leftarrow": "<-",
}

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
    "\u2297": "otimes",
    "\u2032": "'",
    "\u2033": "''",
}

_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_REPLACEMENTS))


@dataclass(slots=True)
class InlineToken:
    kind: str
    text: str


@dataclass(slots=True)
class ExportBlock:
    kind: str
    text: str = ""
    level: int = 0
    tokens: list[InlineToken] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def shorten_paragraph_id(paragraph_id: str) -> str:
    """Return the human-readable part of a paragraph ID.

    Full IDs stored in the DB are prefixed with an 8-char hex chunk hash,
    e.g. ``b081c7f5_P16``.  For display in exports we only need ``P16``.
    Plain IDs without a prefix (legacy format) are returned unchanged.
    """
    if "_" in paragraph_id:
        return paragraph_id.split("_", 1)[1]
    return paragraph_id


def extract_citation_ids(text: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for match in _CITATION_TAG.findall(text or ""):
        citation = match.strip("[]")
        if citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return citations


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    # Accept any line with at least one pipe, or multiple tabs, unless it's a clear heading
    return ("|" in stripped or stripped.count("\t") >= 2) and not stripped.startswith("#")


def _is_heading_line(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_list_line(line: str) -> bool:
    return bool(_MD_LIST_MARKER.match(line) or _MD_NUMBERED_LIST.match(line))


def _cleanup_spacing(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([({\[])[ \t]+", r"\1", text)
    text = re.sub(r"[ \t]+([)}\]])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _join_paragraph_lines(lines: list[str]) -> str:
    if not lines:
        return ""

    merged = lines[0].strip()
    for line in lines[1:]:
        clean_line = line.strip()
        if not clean_line:
            continue
        if merged.endswith("-"):
            merged = merged[:-1] + clean_line
        else:
            merged = f"{merged} {clean_line}"
    return _cleanup_spacing(merged)


def _strip_math_wrappers(text: str) -> str:
    stripped = text.strip()
    for prefix, suffix in ((r"\$", r"\$"), ("$", "$"), (r"\(", r"\)"), (r"\[", r"\]")):
        if stripped.startswith(prefix) and stripped.endswith(suffix):
            return stripped[len(prefix):-len(suffix)].strip()
    return stripped


def _normalize_math_to_text(text: str) -> str:
    content = _strip_math_wrappers(text)
    content = re.sub(r"\\text\{([^}]*)\}", r"\1", content)
    content = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", content)
    content = re.sub(r"\\operatorname\{([^}]*)\}", r"\1", content)
    for latex, replacement in _LATEX_TO_UNICODE.items():
        content = content.replace(latex, replacement)
    content = content.replace("{", "").replace("}", "")
    content = re.sub(r"\\([A-Za-z]+)", r"\1", content)
    content = content.replace("^", "^").replace("_", "_")
    return _cleanup_spacing(content)


def _cleanup_plain_segment(text: str) -> str:
    text = text.replace("\\*", "*").replace("\\_", "_").replace("\\$", "$")
    text = text.replace("**", "").replace("__", "")
    return _cleanup_spacing(text)


def _normalize_source_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Do NOT convert <br> to \n here as it breaks pipe-table parsing by splitting rows.
    # The table parser handles <br> as inline content.
    # text = text.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    # Strip the disclaimer note before further processing so it never reaches
    # the exported document body.
    text = _DISCLAIMER_RE.sub("", text)
    text = _MD_IMAGE.sub("", text)
    text = _MD_CODE_BLOCK.sub("", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    text = _MD_HR.sub("", text)
    text = _PARA_ID_TAG.sub("", text)

    output_lines: list[str] = []
    paragraph_buffer: list[str] = []

    def flush_buffer() -> None:
        paragraph = _join_paragraph_lines(paragraph_buffer)
        if paragraph:
            output_lines.append(paragraph)
        paragraph_buffer.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_buffer()
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            continue

        # Convert tab-separated lines to pipe-separated for the table parser
        if "\t" in line and "|" not in line and line.count("\t") >= 2:
            line = "|" + line.replace("\t", "|") + "|"

        # Repair logic: if this line starts with a citation and the previous line was a paragraph or table,
        # it was likely accidentally wrapped by the LLM. Join it back.
        if _CITATION_TAG.match(line):
            if paragraph_buffer:
                paragraph_buffer[-1] = f"{paragraph_buffer[-1]} {line}"
                continue
            elif output_lines and (_is_table_line(output_lines[-1]) or not output_lines[-1].startswith("#")):
                output_lines[-1] = f"{output_lines[-1]} {line}"
                continue

        if _is_heading_line(line) or _is_list_line(line) or _is_table_line(line):
            flush_buffer()
            output_lines.append(line)
            continue

        paragraph_buffer.append(line)

    flush_buffer()

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    normalized = "\n".join(output_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def parse_inline_tokens(text: str) -> list[InlineToken]:
    normalized = text or ""
    tokens: list[InlineToken] = []
    last_index = 0

    for match in _INLINE_PATTERN.finditer(normalized):
        start, end = match.span()
        if start > last_index:
            plain = _cleanup_plain_segment(normalized[last_index:start])
            if plain:
                tokens.append(InlineToken(kind="text", text=plain))

        segment = match.group(0)
        if segment.startswith("**") and segment.endswith("**"):
            value = _cleanup_plain_segment(segment[2:-2])
            if value:
                tokens.append(InlineToken(kind="bold", text=value))
        elif segment.startswith("*") and segment.endswith("*"):
            value = _cleanup_plain_segment(segment[1:-1])
            if value:
                tokens.append(InlineToken(kind="italic", text=value))
        else:
            value = _normalize_math_to_text(segment)
            if value:
                tokens.append(InlineToken(kind="math", text=value))

        last_index = end

    if last_index < len(normalized):
        plain = _cleanup_plain_segment(normalized[last_index:])
        if plain:
            tokens.append(InlineToken(kind="text", text=plain))

    return tokens


def inline_tokens_to_text(tokens: list[InlineToken]) -> str:
    parts: list[str] = []
    for token in tokens:
        value = token.text.strip()
        if not value:
            continue
        if parts and not parts[-1].endswith(("(", "[", "{")) and not value.startswith((")", "]", "}", ",", ".", ";", ":", "!", "?")):
            parts.append(" ")
        parts.append(value)
    return _cleanup_spacing("".join(parts))


def _split_table_row(line: str, raw: bool = False) -> list[str]:
    stripped = line.strip().strip("|")
    if raw:
        return [cell.strip() for cell in stripped.split("|")]
    return [inline_tokens_to_text(parse_inline_tokens(cell.strip())) for cell in stripped.split("|")]


def build_export_blocks(text: str, raw_cells: bool = False) -> list[ExportBlock]:
    normalized = _normalize_source_text(text)
    if not normalized:
        return []

    lines = normalized.split("\n")
    blocks: list[ExportBlock] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if _is_table_line(line) and index + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[index + 1].strip()):
            headers = _split_table_row(line, raw=raw_cells)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and _is_table_line(lines[index]):
                row = _split_table_row(lines[index], raw=raw_cells)
                if row:
                    rows.append(row)
                index += 1
            blocks.append(ExportBlock(kind="table", headers=headers, rows=rows))
            continue

        if _is_heading_line(line):
            level = len(line) - len(line.lstrip("#"))
            heading_text = inline_tokens_to_text(parse_inline_tokens(line[level:].strip()))
            blocks.append(
                ExportBlock(
                    kind="heading",
                    text=heading_text,
                    level=max(1, min(level, 6)),
                    tokens=parse_inline_tokens(heading_text),
                )
            )
            index += 1
            continue

        if _is_list_line(line):
            bullet_text = _MD_LIST_MARKER.sub("", line)
            bullet_text = _MD_NUMBERED_LIST.sub("", bullet_text)
            tokens = parse_inline_tokens(bullet_text)
            blocks.append(
                ExportBlock(kind="bullet", text=inline_tokens_to_text(tokens), tokens=tokens)
            )
            index += 1
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line or _is_heading_line(next_line) or _is_list_line(next_line):
                break
            if _is_table_line(next_line) and index + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[index + 1].strip()):
                break
            paragraph_lines.append(next_line)
            index += 1

        paragraph = _join_paragraph_lines(paragraph_lines)
        tokens = parse_inline_tokens(paragraph)
        blocks.append(ExportBlock(kind="paragraph", text=inline_tokens_to_text(tokens), tokens=tokens))

    return blocks


def strip_markdown(text: str) -> str:
    lines: list[str] = []
    for block in build_export_blocks(text):
        if block.kind == "heading":
            lines.append(block.text)
        elif block.kind == "bullet":
            lines.append(f"- {block.text}")
        elif block.kind == "table":
            for row in block.rows:
                pairs = []
                for idx, cell in enumerate(row):
                    label = block.headers[idx] if idx < len(block.headers) else f"Column {idx + 1}"
                    pairs.append(f"{label}: {cell}")
                lines.append(" | ".join(pairs))
        else:
            lines.append(block.text)
    return "\n\n".join(line for line in lines if line).strip()


def format_structured_text(text: str) -> str:
    lines: list[str] = []
    for block in build_export_blocks(text):
        if block.kind == "heading":
            heading = block.text.upper() if block.level <= 2 else block.text
            lines.append(heading)
        elif block.kind == "bullet":
            lines.append(f"- {block.text}")
        elif block.kind == "table":
            if block.headers:
                lines.append(" | ".join(block.headers))
            for row in block.rows:
                padded = row + [""] * max(0, len(block.headers) - len(row))
                lines.append(" | ".join(padded[:len(block.headers)] if block.headers else row))
        else:
            lines.append(block.text)
    return "\n\n".join(line for line in lines if line).strip()


def sanitize_for_pdf(text: str) -> str:
    text = _UNICODE_RE.sub(lambda m: _UNICODE_REPLACEMENTS[m.group()], text)
    output: list[str] = []
    for char in text:
        try:
            char.encode("latin-1")
            output.append(char)
        except UnicodeEncodeError:
            decomposed = unicodedata.normalize("NFKD", char)
            ascii_approx = decomposed.encode("ascii", "ignore").decode("ascii")
            output.append(ascii_approx if ascii_approx else "?")
    return "".join(output)


def clean_for_export(text: str) -> str:
    return sanitize_for_pdf(strip_markdown(text))
