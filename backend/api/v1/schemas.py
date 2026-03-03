"""TraceLit — Pydantic API Schemas for v1.

Request/response models defining the contract between frontend and backend.
All API v1 endpoints use these for validation and serialization.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Request Models
# ============================================================

class ChatQueryRequest(BaseModel):
    """Request body for the chat query endpoint."""

    query: str = Field(..., max_length=2000, description="User's question")
    session_id: str
    active_paper_ids: Optional[List[str]] = Field(
        default=None,
        description="Filter by specific papers; None = all session papers",
    )


class SessionCreateRequest(BaseModel):
    """Request body for creating a new session."""

    name: Optional[str] = "Untitled Session"
    paper_ids: List[str] = Field(default_factory=list)


class SessionUpdateRequest(BaseModel):
    """Request body for updating a session."""

    name: Optional[str] = None
    paper_ids: Optional[List[str]] = None


class ComparisonUpdateRequest(BaseModel):
    """Request body for updating a comparison table cell (Phase 2)."""

    paper_id: str
    field: str  # problem | method | dataset | metrics | results
    value: str


class ExportRequest(BaseModel):
    """Request body for export endpoints."""

    session_id: str
    format: Optional[str] = "pdf"  # "pdf" | "excel" | "session-excel"


# ============================================================
# Response Models — Papers
# ============================================================

class PaperUploadResponse(BaseModel):
    """Response after uploading PDFs."""

    status: str = "processing"
    paper_ids: List[str]
    websocket_url: str = "/ws/papers/progress"


class PaperSchema(BaseModel):
    """Paper metadata for list/detail endpoints."""

    id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    pages: Optional[int] = None
    status: str
    upload_date: str
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class SentenceSchema(BaseModel):
    """Individual sentence within a paragraph."""

    sentence_id: str  # "P5_S2"
    text: str
    start_char: int
    end_char: int
    tokens: int = 0


class ParagraphSchema(BaseModel):
    """Paragraph with sentence map."""

    paragraph_id: str  # "P5"
    text: str
    section: str
    page: int
    sentences: List[SentenceSchema] = Field(default_factory=list)


class SectionSchema(BaseModel):
    """Section within a paper."""

    id: int
    title: str
    page_start: Optional[int] = None
    order: int


class PaperContentResponse(BaseModel):
    """Full paper content with sections and paragraphs."""

    paper_id: str
    title: str
    sections: List[SectionSchema] = Field(default_factory=list)
    paragraphs: List[ParagraphSchema] = Field(default_factory=list)
    total_paragraphs: int = 0
    total_sentences: int = 0


# ============================================================
# Response Models — Chat & HAVF
# ============================================================

class CitationSource(BaseModel):
    """A single citation source linking to a specific sentence in a paper."""

    paragraph_id: str   # e.g. "P5"
    sentence_id: str    # e.g. "P5_S2"
    paper_id: str
    paper_title: str
    section: str
    page: int
    matched_text: str   # The specific source sentence (≤ 300 chars)


class SentenceVerification(BaseModel):
    """HAVF verification result for a single generated sentence."""

    text: str                                          # Generated sentence text
    citations: List[str] = Field(default_factory=list)  # ["P5", "P12"]
    confidence: float                                  # 0.0 – 1.0
    level: str                                         # "high" | "medium" | "low"
    method: str  # "embedding_similarity" | "cross_encoder_rerank" | "automatic_fallback"
    sources: List[CitationSource] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Full chat response with HAVF-verified sentences."""

    message_id: str
    query: str
    text: str                                              # Full response text
    sentences: List[SentenceVerification] = Field(default_factory=list)
    overall_confidence: float = 0.0
    provider: str                                          # "gemini" | "groq" | "ollama"
    warning: Optional[str] = None                         # Fallback attribution warning
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Response Models — Sessions
# ============================================================

class SessionSchema(BaseModel):
    """Session metadata."""

    id: str
    name: str
    created_at: str
    updated_at: Optional[str] = None
    paper_ids: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ============================================================
# Response Models — Generic
# ============================================================

class ErrorResponse(BaseModel):
    """Standardised error response — never raw stack traces."""

    error: Dict[str, Any] = Field(
        ...,
        description="Error details with code, message, details",
    )
    status: str = "error"


# ============================================================
# Response Models — Comparison
# ============================================================

class ContributionEntry(BaseModel):
    """A single contribution field value with source."""

    value: str = "Not specified"
    source: str = ""


class PaperContributions(BaseModel):
    """Structured contributions for a single paper."""

    problem: ContributionEntry = Field(default_factory=ContributionEntry)
    method: ContributionEntry = Field(default_factory=ContributionEntry)
    dataset: ContributionEntry = Field(default_factory=ContributionEntry)
    metrics: ContributionEntry = Field(default_factory=ContributionEntry)
    results: ContributionEntry = Field(default_factory=ContributionEntry)


class ComparisonRow(BaseModel):
    """A single row in the comparison table."""

    field: str
    papers: Dict[str, ContributionEntry] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    """Full comparison table response."""

    session_id: str
    papers: List[Dict[str, Any]] = Field(default_factory=list)
    contributions: Dict[str, Any] = Field(default_factory=dict)
    rows: List[ComparisonRow] = Field(default_factory=list)


# ============================================================
# Response Models — Analysis (Phase 2)
# ============================================================

class KeywordResponse(BaseModel):
    """Keywords extracted from a paper."""

    paper_id: str
    keywords: List[str] = Field(default_factory=list)
    cached: bool = False


class SummaryResponse(BaseModel):
    """Generated paper summary."""

    paper_id: str
    summary: Optional[str] = None
    has_summary: bool = False


class LiteratureReviewResponse(BaseModel):
    """Generated literature review."""

    session_id: str
    review: str
    focus_area: Optional[str] = None


class ResearchGapEntry(BaseModel):
    """A single identified research gap."""

    gap_title: str
    description: str
    papers_affected: List[str] = Field(default_factory=list)
    severity: str = "medium"
    cluster_size: int = 0
    limitations: List[Dict[str, str]] = Field(default_factory=list)


class ResearchGapsResponse(BaseModel):
    """Research gaps analysis result."""

    session_id: str
    gaps: List[ResearchGapEntry] = Field(default_factory=list)
    total_limitations_found: int = 0
    clusters_formed: int = 0
    papers_analyzed: int = 0


# ============================================================
# Response Models — Processing Status
# ============================================================

class ProcessingJobStatus(BaseModel):
    """Status of a single paper processing job."""

    paper_id: str
    stage: str  # queued | extracting | chunking | embedding | indexing | complete | failed
    progress: float = 0.0
    error: Optional[str] = None


class ProcessingQueueStatus(BaseModel):
    """Status of the paper processing queue."""

    active_count: int = 0
    queue_size: int = 0
    jobs: Dict[str, ProcessingJobStatus] = Field(default_factory=dict)
