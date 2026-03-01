"""TraceLit — Text processing utilities."""

import re
from typing import List


def estimate_tokens(text: str) -> int:
    """Rough token estimate — 1 token ≈ 4 chars for English text."""
    return len(text) // 4


def clean_whitespace(text: str) -> str:
    """Collapse multiple spaces and strip leading/trailing whitespace."""
    return re.sub(r"  +", " ", text).strip()


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens tokens."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def split_sentences_naive(text: str) -> List[str]:
    """Naively split text on sentence-ending punctuation.

    Use SentenceAwareChunker for production splitting — this is
    for quick one-off uses where full chunker setup is overkill.
    """
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]
