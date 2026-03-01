import os
import shutil
from pathlib import Path

from shared.constants import UPLOADS_DIR, EXPORTS_DIR, FAISS_INDEX_DIR


def ensure_directories() -> None:
    """Create data directories if they don't exist."""
    for directory in (UPLOADS_DIR, EXPORTS_DIR, FAISS_INDEX_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)


def save_upload(content: bytes, filename: str) -> Path:
    """
    Persist raw upload bytes to disk.
    Returns the resolved path.
    """
    dest = Path(UPLOADS_DIR) / filename
    dest.write_bytes(content)
    return dest


def delete_file(path: str | Path) -> bool:
    """Delete a single file, return True if it existed."""
    p = Path(path)
    if p.is_file():
        p.unlink()
        return True
    return False


def delete_directory(path: str | Path) -> bool:
    """Recursively delete a directory, return True if it existed."""
    p = Path(path)
    if p.is_dir():
        shutil.rmtree(p)
        return True
    return False


def get_file_size_mb(path: str | Path) -> float:
    """Return size of *path* in megabytes."""
    return os.path.getsize(path) / (1024 * 1024)
