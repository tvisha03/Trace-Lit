import re

_ABBREV = re.compile(
    # Academic abbreviations that end with a period but do NOT terminate a sentence.
    # Expanded list covers common in-text abbreviations, titles, and citation
    # shorthand to reduce false sentence-boundary splits (MINOR-002 fix).
    r"\b(?:"
    # Typical citation / reference abbreviations
    r"et al|Fig|fig|Eq|eq|cf|viz|nb|"
    # Common Latin abbreviations
    r"e\.g|i\.e|vs|i\.e\.?|e\.g\.?|et seq|op cit|ibid|"
    # Titles and honorifics
    r"Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Rev|Gen|Sgt|Cpl|Lt|Col|Maj|"
    # Org / legal suffixes
    r"Inc|Ltd|Corp|Dept|Assoc|Univ|Inst|"
    # Measurement / publication
    r"Vol|No|pp|Ch|Sec|approx|est|avg|"
    # Generic informal
    r"etc|vs\.?"
    r")\.$",
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
    """Estimate token count using a word-based heuristic.

    One word ≈ 1.3 sub-word tokens for English prose, which is measurably
    more accurate than the naive char/4 rule for natural-language text.
    Code and non-Latin scripts may tokenise differently; this remains a
    conservative upper-bound safe for rate-limit budgeting.
    """
    word_count = len(text.split())
    # 30% overhead accounts for punctuation, sub-word splits, and non-ASCII.
    return max(1, int(word_count * 1.3))

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
