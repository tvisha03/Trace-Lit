"""TraceLit — Chat Engine.

Query classification and retrieval configuration.
Advanced query type router with regex pattern matching
and per-type retrieval strategies.
"""

import re
from typing import Dict, List

from loguru import logger


# ============================================================
# Query Type Configuration
# ============================================================

QUERY_TYPE_CONFIG: Dict[str, Dict] = {
    "factual": {"top_k": 5, "havf_level": "full", "description": "Direct factual questions"},
    "comparison": {"top_k": 3, "havf_level": "full", "description": "Compare multiple papers/methods"},
    "summary": {"top_k": 8, "havf_level": "basic", "description": "Summarize content"},
    "methodology": {"top_k": 5, "havf_level": "full", "description": "Method/approach questions"},
    "multi_hop": {"top_k": 6, "havf_level": "full", "description": "Questions requiring cross-paper reasoning"},
    "follow_up": {"top_k": 3, "havf_level": "basic", "description": "Continuation of previous exchange"},
    "metadata": {"top_k": 2, "havf_level": "none", "description": "Questions about paper metadata"},
    "exploratory": {"top_k": 5, "havf_level": "basic", "description": "Open-ended exploration"},
}


# ============================================================
# Regex Pattern Collections
# ============================================================

_COMPARISON_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(compare|comparison|contrast|differ(?:ence|ent|s)?|vs\.?|versus)\b", re.I),
    re.compile(r"\b(similar(?:ity|ities)?|distinct(?:ion)?|advantage|disadvantage)\b", re.I),
    re.compile(r"\bhow\s+(?:does|do)\s+.+\s+(?:differ|compare)\b", re.I),
    re.compile(r"\bwhich\s+(?:is|are)\s+better\b", re.I),
]

_SUMMARY_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(summarize|summary|overview|main\s+points|key\s+(?:findings|takeaways|contributions))\b", re.I),
    re.compile(r"\b(what\s+(?:is|are)\s+(?:the\s+)?(?:main|key|primary))\b", re.I),
    re.compile(r"\b(gist|brief|outline|recap|abstract)\b", re.I),
    re.compile(r"\bin\s+(?:a\s+)?(?:few\s+words|brief|short)\b", re.I),
]

_METHODOLOGY_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(method(?:ology)?|approach|technique|algorithm|pipeline|architecture)\b", re.I),
    re.compile(r"\bhow\s+(?:did|do|does)\s+(?:they|the\s+authors?|it)\b", re.I),
    re.compile(r"\b(implement(?:ation)?|design(?:ed)?|train(?:ing|ed)?|model\s+architecture)\b", re.I),
    re.compile(r"\b(loss\s+function|objective|optimization|hyperparameter)\b", re.I),
]

_MULTI_HOP_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(across|between|both|all)\s+(?:the\s+)?papers?\b", re.I),
    re.compile(r"\b(common\s+(?:thread|theme|finding)|shared|overlap)\b", re.I),
    re.compile(r"\bhow\s+(?:do|does)\s+(?:the\s+)?(?:findings|results)\s+(?:relate|connect)\b", re.I),
    re.compile(r"\bcombining|synthesize|integrate\b", re.I),
]

_FOLLOW_UP_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(what\s+about|and\s+(?:how|what)|also|additionally|furthermore)\b", re.I),
    re.compile(r"^(related\s+to\s+that|on\s+that\s+note|speaking\s+of)\b", re.I),
    re.compile(r"\b(you\s+(?:just\s+)?(?:said|mentioned)|previous(?:ly)?|earlier|above)\b", re.I),
    re.compile(r"^(can\s+you\s+(?:elaborate|expand|explain\s+more))\b", re.I),
]

_METADATA_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(who\s+(?:are\s+)?(?:the\s+)?authors?|written\s+by|published)\b", re.I),
    re.compile(r"\b(when\s+was\s+(?:it|this)\s+published|year|date|journal|conference|venue)\b", re.I),
    re.compile(r"\b(how\s+many\s+(?:pages|sections|references))\b", re.I),
    re.compile(r"\b(title\s+of|paper\s+(?:title|name))\b", re.I),
]


def classify_query_type(query: str) -> str:
    """Classify a user query into a type for retrieval tuning.

    Uses regex pattern matching with priority ordering.
    Falls back to 'factual' as the default for academic Q&A.

    Args:
        query: User query string.

    Returns:
        Query type: factual | comparison | summary | methodology |
        multi_hop | follow_up | metadata | exploratory.
    """
    lower = query.lower().strip()

    # Priority order: follow_up → metadata → comparison → multi_hop → methodology → summary → factual
    pattern_groups = [
        ("follow_up", _FOLLOW_UP_PATTERNS),
        ("metadata", _METADATA_PATTERNS),
        ("comparison", _COMPARISON_PATTERNS),
        ("multi_hop", _MULTI_HOP_PATTERNS),
        ("methodology", _METHODOLOGY_PATTERNS),
        ("summary", _SUMMARY_PATTERNS),
    ]

    for query_type, patterns in pattern_groups:
        for pattern in patterns:
            if pattern.search(lower):
                logger.debug("Query classified as '{}' via pattern: {}", query_type, pattern.pattern[:40])
                return query_type

    # Check for very short or vague queries → exploratory
    if len(lower.split()) <= 3 and not lower.endswith("?"):
        return "exploratory"

    # Default: factual (most common for academic Q&A)
    return "factual"


def get_retrieval_config(query_type: str) -> Dict:
    """Return retrieval configuration for a given query type.

    Args:
        query_type: Result of classify_query_type().

    Returns:
        Dict with top_k, havf_level, and description keys.
    """
    config = QUERY_TYPE_CONFIG.get(query_type, QUERY_TYPE_CONFIG["factual"])
    logger.debug("Query type '{}' → top_k={}, havf_level={}", query_type, config["top_k"], config["havf_level"])
    return config
