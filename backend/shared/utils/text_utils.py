import re

_ABBREV = re.compile(
    r"\b(?:et al|Fig|fig|Eq|eq|e\.g|i\.e|vs|Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Inc|Ltd|Corp|Dept|Vol|No|Rev)\.$",
    re.IGNORECASE,
)

_CITATION_END = re.compile(r"\]\.\s*$")

def split_into_sentences(text: str) -> list[str]:
    raw_splits = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text)

    sentences: list[str] = []
    buffer = ""

    for fragment in raw_splits:
        buffer = f"{buffer} {fragment}".strip() if buffer else fragment

        if _ABBREV.search(buffer):
            continue

        if re.search(r"\d\.\d\s*$", buffer):
            continue

        sentences.append(buffer)
        buffer = ""

    if buffer:
        sentences.append(buffer)

    return [s.strip() for s in sentences if s.strip()]

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def truncate_text(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")

def extract_paragraph_ids(text: str) -> list[str]:
    return re.findall(r"\[P(\d+)\]", text)

def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
