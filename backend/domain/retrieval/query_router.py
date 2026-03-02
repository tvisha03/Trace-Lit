
import re
from dataclasses import dataclass

from shared.enums import QueryType
from shared.logger import get_logger

logger = get_logger(__name__)

# Maximum query length accepted by the classifier.  Truncating here prevents
# pathologically-large inputs from inflating pattern-match costs or bypassing
# classification by burying keywords deep in noisy content.
_MAX_QUERY_CHARS = 5_000


def _sanitize_query(query: str) -> str:
    """Strip control characters and cap length before pattern matching.

    User queries pass through the classifier before being forwarded to the
    LLM.  Sanitising at this layer prevents malformed input from influencing
    retrieval behaviour through classifier side-effects.
    """
    # Remove null bytes and non-printable control characters while keeping
    # standard whitespace (\n, \r, \t) that appear legitimately in queries.
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)
    return sanitized[:_MAX_QUERY_CHARS]

_COMPARISON_PATTERNS = re.compile(
    r"\b(compar|differ|similar|contrast|versus|vs\.?|between|distinguish|relate)\b",
    re.IGNORECASE,
)

_SUMMARY_PATTERNS = re.compile(
    r"\b(summar|overview|outline|describe|explain.*paper|what is.*paper|"
    r"gist|brief|tl;?dr|recap|main points?)\b",
    re.IGNORECASE,
)

_MULTI_HOP_PATTERNS = re.compile(
    r"\b(which papers?|across|all papers?|each paper|how many papers?|"
    r"every paper|common|shared|overlap)\b",
    re.IGNORECASE,
)

_METADATA_PATTERNS = re.compile(
    r"\b(who wrote|author|year|published|title of|journal|conference|"
    r"when was|date|doi|abstract of|affiliat)\b",
    re.IGNORECASE,
)

_FOLLOW_UP_PATTERNS = re.compile(
    r"\b(more about|elaborate|expand|tell me more|what about|"
    r"can you explain|go deeper|clarify|that|this|the same)\b",
    re.IGNORECASE,
)

_SPECIFIC_PAPER_REF = re.compile(r"\bpaper\s*#?\d+\b", re.IGNORECASE)

@dataclass
class QueryClassification:
    query_type: QueryType
    confidence: float
    target_paper_ids: list[str] | None = None
    retrieval_top_k: int | None = None
    balanced: bool = False

_PATTERN_RULES: list[tuple[re.Pattern, QueryType, float]] = [
    (_COMPARISON_PATTERNS, QueryType.COMPARISON, 0.7),
    (_SUMMARY_PATTERNS, QueryType.SUMMARY, 0.7),
    (_MULTI_HOP_PATTERNS, QueryType.MULTI_HOP, 0.6),
    (_METADATA_PATTERNS, QueryType.METADATA, 0.8),
    (_FOLLOW_UP_PATTERNS, QueryType.FOLLOW_UP, 0.5),
]

def _apply_contextual_boosts(
    scores: dict[QueryType, float],
    query: str,
    query_lower: str,
    history: list | None,
    paper_count: int,
) -> None:
    has_paper_ref = bool(_SPECIFIC_PAPER_REF.search(query))
    if has_paper_ref:
        if paper_count > 1:
            scores[QueryType.COMPARISON] += 0.2
        scores[QueryType.SUMMARY] += 0.2

    word_count = len(query_lower.split())
    if word_count <= 8:
        scores[QueryType.FOLLOW_UP] += 0.2

    _apply_follow_up_boost(scores, query_lower, word_count, history)

def _apply_follow_up_boost(
    scores: dict[QueryType, float],
    query_lower: str,
    word_count: int,
    history: list | None,
) -> None:
    if not history or word_count > 5:
        return
    if re.search(r"\b(that|this|it|they)\b", query_lower):
        scores[QueryType.FOLLOW_UP] += 0.4

def _compute_scores(
    query: str,
    query_lower: str,
    history: list | None,
    paper_count: int,
) -> dict[QueryType, float]:
    scores: dict[QueryType, float] = {qt: 0.0 for qt in QueryType}
    scores[QueryType.SIMPLE_QA] = 0.3

    for pattern, qtype, base_score in _PATTERN_RULES:
        if pattern.search(query):
            scores[qtype] += base_score

    _apply_contextual_boosts(scores, query, query_lower, history, paper_count)
    return scores

def classify_query(
    query: str,
    history: list | None = None,
    paper_count: int = 1,
) -> QueryClassification:
    # Sanitize before any pattern matching so control characters and
    # oversized payloads cannot influence classification outcomes.
    query = _sanitize_query(query)
    query_lower = query.lower().strip()

    scores = _compute_scores(query, query_lower, history, paper_count)

    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    classification = _build_classification(best_type, best_score, paper_count)

    logger.info(
        f"Query classified as {classification.query_type.value} "
        f"(confidence={classification.confidence:.2f}): {query[:80]}"
    )
    return classification

_ROUTING_HINTS: dict[QueryType, tuple[int, bool]] = {
    QueryType.COMPARISON: (3, True),
    QueryType.SUMMARY: (15, False),
    QueryType.MULTI_HOP: (6, False),
    QueryType.METADATA: (0, False),
    QueryType.FOLLOW_UP: (4, False),
    QueryType.SIMPLE_QA: (4, False),
}

def _build_classification(
    query_type: QueryType,
    confidence: float,
    paper_count: int,
) -> QueryClassification:
    top_k, balanced = _ROUTING_HINTS.get(query_type, (4, False))
    return QueryClassification(
        query_type=query_type,
        confidence=min(confidence, 1.0),
        retrieval_top_k=top_k,
        balanced=balanced,
    )
