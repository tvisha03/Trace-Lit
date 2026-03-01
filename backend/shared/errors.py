class TraceLitError(Exception):
    """Base exception for all TraceLit errors."""

    def __init__(self, message: str = "An unexpected error occurred", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# ── LLM / Provider errors ─────────────────────────────────────────────────

class RateLimitError(TraceLitError):
    """API provider returned 429 — switch provider immediately (no retry)."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"Rate limit reached for {provider}",
            status_code=429,
        )
        self.provider = provider


class ProviderTimeoutError(TraceLitError):
    """LLM provider did not respond within the configured timeout."""

    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            message=f"{provider} timed out after {timeout_seconds}s",
            status_code=504,
        )
        self.provider = provider


class AllProvidersFailedError(TraceLitError):
    """Every provider in the fallback chain failed."""

    def __init__(self) -> None:
        super().__init__(
            message="All AI providers are temporarily unavailable. Please try again in 60 seconds.",
            status_code=503,
        )


class EmptyResponseError(TraceLitError):
    """LLM returned an empty or whitespace-only response."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"{provider} returned an empty response",
            status_code=502,
        )
        self.provider = provider


# ── Citation / Verification errors ─────────────────────────────────────────

class InvalidCitationError(TraceLitError):
    """LLM produced a [P#] that does not exist in the retrieved context."""

    def __init__(self, paragraph_id: str):
        super().__init__(
            message=f"Citation references unknown paragraph: {paragraph_id}",
            status_code=422,
        )
        self.paragraph_id = paragraph_id


# ── PDF / Extraction errors ────────────────────────────────────────────────

class PDFExtractionError(TraceLitError):
    """PDF could not be parsed — corrupt, scanned, or password-protected."""

    def __init__(self, filename: str, reason: str = "extraction failed"):
        super().__init__(
            message=f"Failed to process '{filename}': {reason}",
            status_code=422,
        )
        self.filename = filename


# ── Storage / Vector errors ────────────────────────────────────────────────

class VectorStoreError(TraceLitError):
    """FAISS index operation failed."""

    def __init__(self, detail: str = "vector store error"):
        super().__init__(
            message=f"Vector store error: {detail}",
            status_code=500,
        )


# ── Upload validation ─────────────────────────────────────────────────────

class FileValidationError(TraceLitError):
    """Uploaded file violates size, count, or type constraints."""

    def __init__(self, detail: str):
        super().__init__(message=detail, status_code=400)


# ── Analysis / Insufficient data ──────────────────────────────────────────────

class InsufficientDataError(TraceLitError):
    """Operation requires more data than currently available (e.g., gap analysis needs ≥2 papers)."""

    def __init__(self, detail: str):
        super().__init__(message=detail, status_code=400)


# ── PDF Export errors ──────────────────────────────────────────────────────

class PDFExportError(TraceLitError):
    """PDF export failed — usually due to missing system dependencies (e.g., GTK+)."""

    def __init__(self, detail: str = "PDF export unavailable"):
        super().__init__(
            message=f"PDF export is currently unavailable: {detail}. "
                   f"Please contact system administrator or try exporting to a different format.",
            status_code=503,
        )


# ── Session / Not-found ───────────────────────────────────────────────────

class NotFoundError(TraceLitError):
    """Requested resource does not exist."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} '{resource_id}' not found",
            status_code=404,
        )
