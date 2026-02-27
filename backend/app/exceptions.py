"""TraceLit — Custom Exception Hierarchy.

The system must NEVER crash. Every error is caught, logged, and handled gracefully.
Every error path must produce a user-friendly result.
"""


class TraceLitError(Exception):
    """Base exception for all TraceLit errors."""

    def __init__(self, message: str, code: str, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class ProviderError(TraceLitError):
    """LLM provider error (rate limit, timeout, etc.)."""
    pass


class RateLimitError(ProviderError):
    """Specific rate limit error — triggers provider fallback."""

    def __init__(self, provider: str, retry_after: int = 60):
        super().__init__(
            message=f"{provider} rate limit exceeded",
            code="RATE_LIMIT",
            details={"provider": provider, "retry_after": retry_after},
        )


class AllProvidersFailedError(TraceLitError):
    """All LLM providers exhausted — no response possible."""

    def __init__(self, errors: list):
        super().__init__(
            message="All LLM providers failed",
            code="ALL_PROVIDERS_FAILED",
            details={"errors": errors},
        )


class InvalidCitationError(TraceLitError):
    """LLM response missing proper citation format."""

    def __init__(self, message: str = "LLM response lacks citation format"):
        super().__init__(
            message=message,
            code="INVALID_CITATION",
        )


class ExtractionError(TraceLitError):
    """PDF extraction failed."""

    def __init__(self, message: str, paper_id: str = ""):
        super().__init__(
            message=message,
            code="EXTRACTION_FAILED",
            details={"paper_id": paper_id},
        )


class PaperNotReadyError(TraceLitError):
    """Paper still processing, not yet queryable."""

    def __init__(self, paper_id: str):
        super().__init__(
            message=f"Paper {paper_id} is still processing",
            code="PAPER_NOT_READY",
            details={"paper_id": paper_id},
        )


class PaperLimitError(TraceLitError):
    """Maximum number of papers per session exceeded."""

    def __init__(self, limit: int):
        super().__init__(
            message=f"Maximum of {limit} papers per session",
            code="PAPER_LIMIT_EXCEEDED",
            details={"limit": limit},
        )


class FileTooLargeError(TraceLitError):
    """Uploaded file exceeds size limit."""

    def __init__(self, filename: str, size_mb: float, limit_mb: int):
        super().__init__(
            message=f"File '{filename}' is {size_mb:.1f}MB (limit: {limit_mb}MB)",
            code="FILE_TOO_LARGE",
            details={
                "filename": filename,
                "size_mb": size_mb,
                "limit_mb": limit_mb,
            },
        )


class InvalidFileError(TraceLitError):
    """Uploaded file is not a valid PDF."""

    def __init__(self, filename: str, reason: str = "Not a valid PDF"):
        super().__init__(
            message=f"Invalid file '{filename}': {reason}",
            code="INVALID_FILE",
            details={"filename": filename, "reason": reason},
        )
