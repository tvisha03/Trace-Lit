"""TraceLit — Utility Helpers.

Common utility functions used across the application.
"""

import uuid
from pathlib import Path
from typing import Optional

from loguru import logger


def generate_id() -> str:
    """Generate a unique UUID string."""
    return str(uuid.uuid4())


def validate_pdf_magic_bytes(file_bytes: bytes) -> bool:
    """Check if file starts with PDF magic bytes (%PDF).

    Args:
        file_bytes: First few bytes of the file.

    Returns:
        True if the file appears to be a valid PDF.
    """
    return file_bytes[:4] == b"%PDF"


def safe_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    Args:
        filename: Original filename from upload.

    Returns:
        Sanitized filename with only safe characters.
    """
    # Keep only alphanumeric, hyphens, underscores, dots
    safe = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in filename
    )
    # Ensure it ends with .pdf
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe


def file_size_mb(file_path: str) -> float:
    """Get file size in megabytes.

    Args:
        file_path: Path to the file.

    Returns:
        File size in MB.
    """
    return Path(file_path).stat().st_size / (1024 * 1024)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis for preview/logging.

    Args:
        text: Input text.
        max_length: Maximum character length.

    Returns:
        Truncated text with '...' if exceeded.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
