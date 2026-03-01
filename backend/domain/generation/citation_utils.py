"""TraceLit — Citation Parsing & Validation Utilities."""

import re
from typing import Dict, List

from loguru import logger

_CITATION_PATTERN = re.compile(r"\[P(\d+)\]")


def extract_citations(text: str) -> List[str]:
    """Extract all [P#] citation IDs from response text.

    Returns:
        List of paragraph IDs like ['P5', 'P12'].
    """
    return [f"P{m}" for m in _CITATION_PATTERN.findall(text)]


def validate_citations(response_text: str, valid_paragraph_ids: set) -> Dict:
    """Check that every [P#] citation exists in the provided context.

    Returns:
        Dict with valid_citations, invalid_citations,
        uncited_factual_sentences, citation_coverage.
    """
    cited_ids = set(extract_citations(response_text))
    invalid_ids = cited_ids - valid_paragraph_ids

    if invalid_ids:
        logger.warning("Hallucinated paragraph IDs: {}", invalid_ids)

    sentences = _split_response_sentences(response_text)
    uncited_factual = [
        s for s in sentences
        if _is_factual_claim(s) and not _CITATION_PATTERN.search(s)
    ]

    valid_count = len(cited_ids - invalid_ids)
    total_count = max(len(cited_ids), 1)

    return {
        "valid_citations": cited_ids - invalid_ids,
        "invalid_citations": invalid_ids,
        "uncited_factual_sentences": uncited_factual,
        "citation_coverage": valid_count / total_count,
    }


def remove_invalid_citations(text: str, invalid_ids: set) -> str:
    """Strip invalid [P#] citations from response text.

    Args:
        text: LLM response text.
        invalid_ids: Set of paragraph IDs to remove (e.g., {'P99'}).

    Returns:
        Cleaned text.
    """
    for pid in invalid_ids:
        num = pid.replace("P", "")
        text = re.sub(rf"\[P{num}\]\s*", "", text)
    return text.strip()


def _split_response_sentences(text: str) -> List[str]:
    """Split LLM response into individual sentences."""
    pattern = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\?|!)\s+"
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def _is_factual_claim(sentence: str) -> bool:
    """Determine if a sentence is a factual claim vs. transitional text."""
    non_factual_prefixes = [
        "in summary", "to summarize", "overall", "in conclusion",
        "based on the above", "the papers discuss", "according to the provided",
        "this information was not found", "not found in the provided",
        "i'm designed to provide",
    ]
    lower = sentence.lower().strip()
    return not any(lower.startswith(prefix) for prefix in non_factual_prefixes)
