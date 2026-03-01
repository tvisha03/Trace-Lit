import re

# Abbreviations that should NOT trigger a sentence split
_ABBREV = re.compile(
    r"\b(?:et al|Fig|fig|Eq|eq|e\.g|i\.e|vs|Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Inc|Ltd|Corp|Dept|Vol|No|Rev)\.$",
    re.IGNORECASE,
)

# Academic citation pattern at end of sentence: "[12]." or "[1, 3]."
_CITATION_END = re.compile(r"\]\.\s*$")


def split_into_sentences(text: str) -> list[str]:
    # Rough split on period/question/exclamation followed by space + uppercase
    raw_splits = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text)

    sentences: list[str] = []
    buffer = ""

    for fragment in raw_splits:
        buffer = f"{buffer} {fragment}".strip() if buffer else fragment

        # Don't split if the fragment ends with a known abbreviation
        if _ABBREV.search(buffer):
            continue

        # Don't split on decimal numbers (e.g. "achieved 93.2")
        if re.search(r"\d\.\d\s*$", buffer):
            continue

        sentences.append(buffer)
        buffer = ""

    if buffer:
        sentences.append(buffer)

    return [s.strip() for s in sentences if s.strip()]


def estimate_tokens(text: str) -> int:
    """Estimate token count using ≈ 4 chars per token heuristic."""
    return max(1, len(text) // 4)


def truncate_text(text: str, max_tokens: int) -> str:
    """Truncate *text* to approximately *max_tokens*."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe for filesystem paths."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")


def extract_paragraph_ids(text: str) -> list[str]:
    """Extract all [P#] citation references from generated text."""
    return re.findall(r"\[P(\d+)\]", text)


def clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip edges."""
    return re.sub(r"\s+", " ", text).strip()
