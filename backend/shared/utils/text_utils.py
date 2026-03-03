import re

_ABBREV = re.compile(
    r"\b(?:"
    r"et al|Fig|fig|Figs|figs|Eq|eq|Eqs|eqs|cf|viz|nb|"
    r"e\.g|i\.e|vs|i\.e\.?|e\.g\.?|et seq|op cit|ibid|"
    r"Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Rev|Gen|Sgt|Cpl|Lt|Col|Maj|St|"
    r"Inc|Ltd|Corp|Dept|Assoc|Univ|Inst|"
    r"Vol|No|pp|Ch|Sec|Sect|approx|est|avg|max|min|"
    r"Tab|Tbl|Ref|Refs|Suppl|Supp|App|"
    r"etc|vs\.?"
    r")\.$",
    re.IGNORECASE,
)

_CITATION_END = re.compile(r"\]\.\s*$")
def _should_skip_buffer(buffer: str) -> bool:
    if _ABBREV.search(buffer):
        return True
    if re.search(r"\d\.\d\s*$", buffer):
        return True
    if re.search(r"(?:Figure|Table|Equation)\s+\d+\.\s*$", buffer, re.IGNORECASE):
        return True
    if _CITATION_END.search(buffer) and len(buffer.split()) < 4:
        return True
    return False
def split_into_sentences(text: str) -> list[str]:
    raw_splits = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text)

    sentences: list[str] = []
    buffer = ""

    for fragment in raw_splits:
        buffer = f"{buffer} {fragment}".strip() if buffer else fragment

        if _should_skip_buffer(buffer):
            continue

        sentences.append(buffer)
        buffer = ""

    if buffer:
        sentences.append(buffer)

    return [s.strip() for s in sentences if s.strip()]

def estimate_tokens(text: str) -> int:
    word_count = len(text.split())
    return max(1, int(word_count * 1.3))

def truncate_text(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"

def sanitize_filename(name: str) -> str:
    import unicodedata
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")

def extract_paragraph_ids(text: str) -> list[str]:
    return re.findall(r"\[((?:[a-f0-9]{1,8}_)?P\d+)\]", text)


def normalize_paragraph_ids(
    cited_ids: set[str], valid_ids: set[str]
) -> tuple[set[str], dict[str, str]]:
    resolved: set[str] = set()
    replacements: dict[str, str] = {}
    for cid in cited_ids:
        if cid in valid_ids:
            resolved.add(cid)
        elif "_" not in cid:
            matches = [vid for vid in valid_ids if vid.endswith(f"_{cid}")]
            if len(matches) == 1:
                resolved.add(matches[0])
                replacements[cid] = matches[0]
            else:
                resolved.add(cid)
        else:
            resolved.add(cid)
    return resolved, replacements

def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

