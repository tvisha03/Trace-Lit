from enum import Enum

class PaperStatus(str, Enum):
    REGISTERED = "registered"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"

class LLMProvider(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OLLAMA = "ollama"

class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class VerificationMethod(str, Enum):
    EMBEDDING_SIMILARITY = "embedding_similarity"
    CROSS_ENCODER_RERANK = "cross_encoder_rerank"
    SKIPPED = "skipped"

class QueryType(str, Enum):
    SIMPLE_QA = "simple_qa"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    MULTI_HOP = "multi_hop"
    FOLLOW_UP = "follow_up"
    METADATA = "metadata"

class ExportFormat(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    BIBTEX = "bibtex"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
