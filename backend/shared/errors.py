class TraceLitError(Exception):

    def __init__(self, message: str = "An unexpected error occurred", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class RateLimitError(TraceLitError):

    def __init__(self, provider: str):
        super().__init__(
            message=f"Rate limit reached for {provider}",
            status_code=429,
        )
        self.provider = provider

class ProviderTimeoutError(TraceLitError):

    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            message=f"{provider} timed out after {timeout_seconds}s",
            status_code=504,
        )
        self.provider = provider

class AllProvidersFailedError(TraceLitError):

    def __init__(self) -> None:
        super().__init__(
            message="All AI providers are temporarily unavailable. Please try again in 60 seconds.",
            status_code=503,
        )

class EmptyResponseError(TraceLitError):

    def __init__(self, provider: str):
        super().__init__(
            message=f"{provider} returned an empty response",
            status_code=502,
        )
        self.provider = provider

class InvalidCitationError(TraceLitError):

    def __init__(self, paragraph_id: str):
        super().__init__(
            message=f"Citation references unknown paragraph: {paragraph_id}",
            status_code=422,
        )
        self.paragraph_id = paragraph_id

class PDFExtractionError(TraceLitError):

    def __init__(self, filename: str, reason: str = "extraction failed"):
        super().__init__(
            message=f"Failed to process '{filename}': {reason}",
            status_code=422,
        )
        self.filename = filename

class VectorStoreError(TraceLitError):

    def __init__(self, detail: str = "vector store error"):
        super().__init__(
            message=f"Vector store error: {detail}",
            status_code=500,
        )

class FileValidationError(TraceLitError):

    def __init__(self, detail: str):
        super().__init__(message=detail, status_code=400)

class InsufficientDataError(TraceLitError):

    def __init__(self, detail: str):
        super().__init__(message=detail, status_code=400)

class PDFExportError(TraceLitError):

    def __init__(self, detail: str = "PDF export unavailable"):
        super().__init__(
            message=f"PDF export is currently unavailable: {detail}. "
                   f"Please contact system administrator or try exporting to a different format.",
            status_code=503,
        )

class NotFoundError(TraceLitError):

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} '{resource_id}' not found",
            status_code=404,
        )


class ForbiddenError(TraceLitError):
    """Raised when a resource exists but does not belong to the caller's scope
    (e.g. a paper that belongs to a different session).  Returns HTTP 403 so
    clients can distinguish 'not found' from 'found but not yours'.
    """

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"Access to {resource} '{resource_id}' is forbidden",
            status_code=403,
        )
