"""TraceLit — Custom Exception Hierarchy.

Re-exports from shared.errors for backward compatibility.
All new code should import directly from shared.errors.
"""

from shared.errors import (  # noqa: F401
    TraceLitError,
    ProviderError,
    RateLimitError,
    AllProvidersFailedError,
    InvalidCitationError,
    ExtractionError,
    PaperNotReadyError,
    PaperLimitError,
    FileTooLargeError,
    InvalidFileError,
)

__all__ = [
    "TraceLitError",
    "ProviderError",
    "RateLimitError",
    "AllProvidersFailedError",
    "InvalidCitationError",
    "ExtractionError",
    "PaperNotReadyError",
    "PaperLimitError",
    "FileTooLargeError",
    "InvalidFileError",
]
