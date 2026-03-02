"""TraceLit — Keyword Extraction using KeyBERT.

Extracts diverse, representative keywords from paper text
using KeyBERT with Maximal Marginal Relevance (MMR) for diversity.
"""

from typing import List, Optional, Tuple

from loguru import logger


# ============================================================
# Lazy-loaded KeyBERT instance
# ============================================================

_kw_model = None


def _get_kw_model():
    """Lazy-load KeyBERT to avoid startup overhead."""
    global _kw_model
    if _kw_model is None:
        try:
            from keybert import KeyBERT
            _kw_model = KeyBERT(model="all-MiniLM-L6-v2")
            logger.info("KeyBERT model loaded (all-MiniLM-L6-v2)")
        except ImportError:
            logger.warning("KeyBERT not installed — keyword extraction disabled")
            return None
    return _kw_model


def extract_keywords(
    text: str,
    top_n: int = 10,
    keyphrase_ngram_range: Tuple[int, int] = (1, 3),
    diversity: float = 0.7,
    use_mmr: bool = True,
) -> List[str]:
    """Extract keywords from text using KeyBERT with MMR diversity.

    Args:
        text: Full paper text or sections concatenated.
        top_n: Number of keywords to extract.
        keyphrase_ngram_range: Min/max n-gram size for keyphrases.
        diversity: MMR diversity parameter (0=similar, 1=diverse).
        use_mmr: Whether to use Maximal Marginal Relevance.

    Returns:
        List of keyword strings, ordered by relevance.
    """
    model = _get_kw_model()
    if model is None:
        return []

    if not text or len(text.strip()) < 50:
        return []

    try:
        # Truncate very long texts to avoid memory issues
        max_chars = 50_000
        if len(text) > max_chars:
            text = text[:max_chars]

        keywords = model.extract_keywords(
            text,
            keyphrase_ngram_range=keyphrase_ngram_range,
            stop_words="english",
            top_n=top_n,
            use_mmr=use_mmr,
            diversity=diversity,
        )

        # keywords is a list of (keyword, score) tuples
        result = [kw for kw, _score in keywords]
        logger.debug("Extracted {} keywords", len(result))
        return result

    except Exception as e:
        logger.error("Keyword extraction failed: {}", e)
        return []


def extract_paper_keywords(sections: List[dict], top_n: int = 10) -> List[str]:
    """Extract keywords from paper sections.

    Concatenates all section texts and runs keyword extraction.

    Args:
        sections: List of section dicts with 'title' and 'paragraphs'.
        top_n: Number of keywords to extract.

    Returns:
        List of keyword strings.
    """
    text_parts = []
    for section in sections:
        if isinstance(section, dict):
            title = section.get("title", "")
            paragraphs = section.get("paragraphs", [])
            if title:
                text_parts.append(title)
            for para in paragraphs:
                if isinstance(para, dict):
                    text_parts.append(para.get("text", ""))
                elif isinstance(para, str):
                    text_parts.append(para)

    full_text = "\n".join(text_parts)
    return extract_keywords(full_text, top_n=top_n)
