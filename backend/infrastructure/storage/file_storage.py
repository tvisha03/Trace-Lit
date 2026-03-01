"""TraceLit — File storage helpers."""

import os
from pathlib import Path

from app.config import settings


def save_upload(paper_id: str, filename: str, content: bytes) -> str:
    """Persist an uploaded file and return its absolute path.

    Args:
        paper_id: UUID of the paper record.
        filename:  Sanitised filename (use shared.utils.file_utils.safe_filename first).
        content:  Raw file bytes.

    Returns:
        Absolute path to the saved file.
    """
    file_path = os.path.join(settings.upload_dir, f"{paper_id}_{filename}")
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


def delete_upload(file_path: str) -> bool:
    """Delete an uploaded file from disk.

    Returns True if the file was deleted, False if it was not found.
    """
    try:
        Path(file_path).unlink(missing_ok=True)
        return True
    except Exception:
        return False
