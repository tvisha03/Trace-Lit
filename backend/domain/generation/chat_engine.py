"""TraceLit — Chat Engine.

Query classification and retrieval configuration.
Moved from app/llm/multi_provider.py.
"""

from typing import Dict

from loguru import logger


# ============================================================
# Query Type Configuration
# ============================================================

QUERY_TYPE_CONFIG: Dict[str, Dict] = {
    "factual": {"top_k": 5, "havf_level": "full"},
    "comparison": {"top_k": 3, "havf_level": "full"},
    "summary": {"top_k": 8, "havf_level": "basic"},
    "methodology": {"top_k": 5, "havf_level": "full"},
    "follow_up": {"top_k": 3, "havf_level": "basic"},
    "exploratory": {"top_k": 5, "havf_level": "basic"},
}


def classify_query_type(query: str) -> str:
    """Classify a user query into a type for retrieval tuning.

    Args:
        query: User query string.

    Returns:
        Query type: factual | comparison | summary | methodology |
        follow_up | exploratory.
    """
    lower = query.lower().strip()

    # Comparison indicators
    if any(
        kw in lower
        for kw in ["compare", "difference", "vs", "versus", "contrast", "similar"]
    ):
        return "comparison"

    # Summary indicators
    if any(kw in lower for kw in ["summarize", "summary", "overview", "main points"]):
        return "summary"

    # Methodology indicators
    if any(
        kw in lower
        for kw in ["method", "approach", "technique", "algorithm", "how did they"]
    ):
        return "methodology"

    # Follow-up indicators
    if any(
        kw in lower
        for kw in ["what about", "also", "additionally", "related to that", "and"]
    ):
        return "follow_up"

    # Factual by default (most common for academic Q&A)
    return "factual"


def get_retrieval_config(query_type: str) -> Dict:
    """Return retrieval configuration for a given query type.

    Args:
        query_type: Result of classify_query_type().

    Returns:
        Dict with top_k and havf_level keys.
    """
    config = QUERY_TYPE_CONFIG.get(query_type, QUERY_TYPE_CONFIG["factual"])
    logger.debug("Query type '{}' → top_k={}, havf_level={}", query_type, config["top_k"], config["havf_level"])
    return config
