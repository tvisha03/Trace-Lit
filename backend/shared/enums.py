"""TraceLit — Shared Enumerations."""

from enum import Enum


class PaperStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class QueryType(str, Enum):
    FACTUAL = "factual"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    METHODOLOGY = "methodology"
    FOLLOW_UP = "follow_up"
    EXPLORATORY = "exploratory"


class ExtractionMode(str, Enum):
    AUTO = "auto"
    FAST = "fast"
    QUALITY = "quality"
