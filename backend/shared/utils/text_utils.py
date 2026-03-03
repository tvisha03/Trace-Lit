import re

_ABBREV = re.compile(
    # Academic abbreviations that end with a period but do NOT terminate a sentence.
    # Expanded list covers common in-text abbreviations, titles, and citation
    # shorthand to reduce false sentence-boundary splits (MINOR-002 fix).
    r"\b(?:"
    # Typical citation / reference abbreviations
    r"et al|Fig|fig|Figs|figs|Eq|eq|Eqs|eqs|cf|viz|nb|"
    # Common Latin abbreviations
    r"e\.g|i\.e|vs|i\.e\.?|e\.g\.?|et seq|op cit|ibid|"
    # Titles and honorifics
    r"Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Rev|Gen|Sgt|Cpl|Lt|Col|Maj|St|"
    # Org / legal suffixes
    r"Inc|Ltd|Corp|Dept|Assoc|Univ|Inst|"
    # Measurement / publication
    r"Vol|No|pp|Ch|Sec|Sect|approx|est|avg|max|min|"
    # Figure/Table references ("Table 1." should not split)
    r"Tab|Tbl|Ref|Refs|Suppl|Supp|App|"
    # Generic informal
    r"etc|vs\.?"
    r")\.$",
    re.IGNORECASE,
)

_CITATION_END = re.compile(r"\]\.\s*$")

def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex-based heuristics.

    Handles common academic edge cases: abbreviations, decimal numbers,
    figure references ("Fig. 1"), equation labels, and inline citations.
    """
    raw_splits = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text)

    sentences: list[str] = []
    buffer = ""

    for fragment in raw_splits:
        buffer = f"{buffer} {fragment}".strip() if buffer else fragment

        # Don't split after known abbreviations (e.g. "et al.")
        if _ABBREV.search(buffer):
            continue

        # Don't split inside decimal numbers (e.g. "3.5")
        if re.search(r"\d\.\d\s*$", buffer):
            continue

        # Don't split after figure/table references like "Figure 1."
        if re.search(r"(?:Figure|Table|Equation)\s+\d+\.\s*$", buffer, re.IGNORECASE):
            continue

        # Don't split after inline citation endings like "[23]."
        if _CITATION_END.search(buffer) and len(buffer.split()) < 4:
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
    # Normalize Unicode (e.g. accented chars) to ASCII-safe representation,
    # then strip filesystem-unsafe characters.
    import unicodedata
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")

def extract_paragraph_ids(text: str) -> list[str]:
    """Extract full paragraph IDs from citation tags.

    Matches both prefixed (``[a2349a01_P5]``) and bare (``[P5]``) formats.
    Returns the inner ID string (e.g. ``'a2349a01_P5'`` or ``'P5'``).
    """
    return re.findall(r"\[((?:[a-f0-9]{1,8}_)?P\d+)\]", text)


def normalize_paragraph_ids(
    cited_ids: set[str], valid_ids: set[str]
) -> tuple[set[str], dict[str, str]]:
    """Resolve short-form paragraph IDs (``P5``) to prefixed equivalents.

    Returns ``(resolved_ids, replacement_map)`` where *replacement_map* maps
    short-form IDs to their prefixed counterpart for text substitution.
    IDs that already appear in *valid_ids* (or have no unambiguous match)
    are kept as-is.
    """
    resolved: set[str] = set()
    replacements: dict[str, str] = {}
    for cid in cited_ids:
        if cid in valid_ids:
            resolved.add(cid)
        elif "_" not in cid:
            # Short form like "P5" — find an unambiguous prefixed match.
            matches = [vid for vid in valid_ids if vid.endswith(f"_{cid}")]
            if len(matches) == 1:
                resolved.add(matches[0])
                replacements[cid] = matches[0]
            else:
                # Ambiguous or no match — flag as-is for invalid detection.
                resolved.add(cid)
        else:
            resolved.add(cid)
    return resolved, replacements

def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
