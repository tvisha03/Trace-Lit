
import re
import uuid as _uuid
from pydantic import BaseModel, Field, field_validator
from typing import Optional

_INJECT_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|prior|all)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+instructions?", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"disregard\s+(all|previous|prior)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"\[INST\]|\[\/INST\]|<\|system\|>|<\|user\|>", re.IGNORECASE),
    re.compile(r"override\s+your\s+(instructions?|programming|guidelines)", re.IGNORECASE),
    re.compile(r"do\s+not\s+(follow|obey|listen\s+to)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"prompt\s+injection", re.IGNORECASE),
    re.compile(r"roleplay\s+as", re.IGNORECASE),
    re.compile(r"pretend\s+to\s+be", re.IGNORECASE),
    re.compile(r"access\s+developer\s+mode", re.IGNORECASE),
]

def _sanitize_user_text(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    if not value:
        raise ValueError("Input must contain visible characters after sanitization.")
    for pattern in _INJECT_PATTERNS:
        if pattern.search(value):
            raise ValueError("Input contains disallowed content.")
    return value

class SessionCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)

class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

class SessionResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]

class WebSocketURLResponse(BaseModel):
    websocket_url: str
    session_id: str

class PaperResponse(BaseModel):
    id: str
    session_id: str
    filename: str
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    status: str
    progress: float = 0.0
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    file_size_mb: Optional[float] = None
    error_message: Optional[str] = None
    created_at: str

class PaperListResponse(BaseModel):
    papers: list[PaperResponse]

class PaperUploadResponse(BaseModel):
    paper_ids: list[str]
    message: str

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    stream: bool = False
    keywords: Optional[list[str]] = Field(
        None,
        max_length=10,
        description="Optional keyword filter — when provided, retrieved context "
                    "is limited to chunks containing at least one of these terms.",
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_user_text(v)

class VerificationItem(BaseModel):
    claim: str
    confidence: str
    score: float
    source_sentence: Optional[str] = None
    paragraph_id: Optional[str] = None
    paper_id: Optional[str] = None
    sentence_key: Optional[str] = None
    verification_method: Optional[str] = None
    chunk_type: Optional[str] = None
    citation_ref: Optional[str] = None

class ChatResponse(BaseModel):
    content: str
    provider: str
    havf_results: list[VerificationItem]
    token_count: int
    latency_ms: float

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    provider: Optional[str] = None
    havf_results: Optional[list[VerificationItem]] = None
    token_count: Optional[int] = None
    latency_ms: Optional[float] = None
    created_at: str

class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: Optional[int] = None
    limit: Optional[int] = None
    offset: Optional[int] = None

class CompareRequest(BaseModel):
    paper_ids: list[str] = Field(..., min_length=2, max_length=7)

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, v: list[str]) -> list[str]:
        for pid in v:
            try:
                _uuid.UUID(pid)
            except ValueError:
                raise ValueError(f"Invalid UUID format for paper_id: {pid}")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate paper_ids are not allowed")
        return v

class ComparisonResponse(BaseModel):
    comparison: str
    paper_ids: list[str]
    paper_titles: list[str]
    provider: str

class ContributionResponse(BaseModel):
    paper_id: str
    title: str
    contributions: dict

class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(pdf|excel|bibtex|docx|latex)$")

class ComparisonExportRequest(BaseModel):
    paper_ids: list[str] = Field(..., min_length=2, max_length=7)
    format: str = Field(default="pdf", pattern="^(pdf|excel|bibtex|docx|latex)$")

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, v: list[str]) -> list[str]:
        for pid in v:
            try:
                _uuid.UUID(pid)
            except ValueError:
                raise ValueError(f"Invalid UUID format for paper_id: {pid}")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate paper_ids are not allowed")
        return v

class ExportResponse(BaseModel):
    download_url: str
    filename: str
    format: str

class KeywordItem(BaseModel):
    keyword: str
    score: float

class KeywordResponse(BaseModel):
    paper_id: str
    keywords: list[KeywordItem]

class ThemeItem(BaseModel):
    label: str
    keywords: list[str]
    papers_covering: Optional[list[str]] = None
    coverage_ratio: float

class GapAnalysisResponse(BaseModel):
    themes: list[ThemeItem]
    underexplored: list[ThemeItem]
    narrative: Optional[str] = None
    provider: Optional[str] = None

class ReviewResponse(BaseModel):
    review: str
    paper_count: int
    provider: str

class SummaryResponse(BaseModel):
    paper_id: str
    title: Optional[str] = None
    summary: str
    provider: str

class VerifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    paper_ids: list[str] = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return _sanitize_user_text(v)

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, v: list[str]) -> list[str]:
        for pid in v:
            try:
                _uuid.UUID(pid)
            except ValueError:
                raise ValueError(f"Invalid UUID format for paper_id: {pid}")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate paper_ids are not allowed")
        return v

class VerifyResponse(BaseModel):
    results: list[VerificationItem]

class HealthResponse(BaseModel):
    status: str
    version: str
    use_local_llm: bool = False
    provider_order: list[str] = []
    providers: dict[str, bool] = {}
    db: bool = False
    faiss: bool = False
    faiss_stats: Optional[dict] = None
    cross_encoder: bool = False

class SSEQueryTypeEvent(BaseModel):
    type: str

class SSESourceItem(BaseModel):
    paragraph_id: str
    paper_id: str
    score: float

class SSETokenEvent(BaseModel):
    token: str

class SSEHavfEvent(BaseModel):
    results: list[VerificationItem]

class SSEDoneEvent(BaseModel):
    provider: str
    full_text: str

class SSEErrorEvent(BaseModel):
    detail: str
