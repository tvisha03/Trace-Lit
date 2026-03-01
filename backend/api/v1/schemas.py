"""
Pydantic schemas for all API request/response models.
Validates input, serialises output, and documents the API contract.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# ─── Session ───────────────────────────────────────────────────────────
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


# ─── Paper ─────────────────────────────────────────────────────────────
class PaperResponse(BaseModel):
    id: str
    session_id: str
    filename: str
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
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


# ─── Chat ──────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    stream: bool = False

class VerificationItem(BaseModel):
    claim: str
    confidence: str
    score: float
    source_sentence: Optional[str] = None
    paragraph_id: Optional[str] = None
    sentence_key: Optional[str] = None

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


# ─── Comparison ────────────────────────────────────────────────────────
class CompareRequest(BaseModel):
    paper_ids: list[str] = Field(..., min_length=2, max_length=7)

class ComparisonResponse(BaseModel):
    comparison: str
    paper_ids: list[str]
    paper_titles: list[str]
    provider: str

class ContributionResponse(BaseModel):
    paper_id: str
    title: str
    contributions: dict


# ─── Export ─────────────────────────────────────────────────────────────
class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(pdf|excel)$")

class ExportResponse(BaseModel):
    download_url: str
    filename: str
    format: str


# ─── Analysis ──────────────────────────────────────────────────────────
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

class ReviewResponse(BaseModel):
    review: str
    paper_count: int
    provider: str


# ─── Verification ──────────────────────────────────────────────────────
class VerifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    paper_ids: list[str] = Field(..., min_length=1)

class VerifyResponse(BaseModel):
    results: list[VerificationItem]


# ─── Health ────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    version: str
    providers: dict[str, bool] = {}
