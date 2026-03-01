"""TraceLit — File utility helpers."""

import uuid
from pathlib import Path


def generate_id() -> str:
    """Generate a unique UUID string."""
    return str(uuid.uuid4())


def validate_pdf_magic_bytes(file_bytes: bytes) -> bool:
    """Check if file starts with PDF magic bytes (%PDF)."""
    return file_bytes[:4] == b"%PDF"


def safe_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    Keeps only alphanumeric, hyphens, underscores, and dots.
    Appends .pdf extension if missing.
    """
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe


def file_size_mb(file_path: str) -> float:
    """Return file size in megabytes."""
    return Path(file_path).stat().st_size / (1024 * 1024)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis for preview / logging."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
