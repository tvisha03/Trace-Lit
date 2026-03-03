import os
import shutil
from pathlib import Path

from shared.constants import UPLOADS_DIR, EXPORTS_DIR, FAISS_INDEX_DIR, MIN_DISK_SPACE_MB
from shared.logger import get_logger

logger = get_logger(__name__)


def ensure_directories() -> None:
    for directory in (UPLOADS_DIR, EXPORTS_DIR, FAISS_INDEX_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)

def save_upload(content: bytes, filename: str) -> Path:
    dest = Path(UPLOADS_DIR) / filename
    dest.write_bytes(content)
    return dest

def delete_file(path: str | Path) -> bool:
    p = Path(path)
    if p.is_file():
        p.unlink()
        return True
    return False

def delete_directory(path: str | Path) -> bool:
    p = Path(path)
    if p.is_dir():
        shutil.rmtree(p)
        return True
    return False

def get_file_size_mb(path: str | Path) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def check_disk_space(path: str | Path = UPLOADS_DIR, min_mb: int = MIN_DISK_SPACE_MB) -> bool:
    try:
        usage = shutil.disk_usage(str(path) if Path(path).exists() else ".")
        free_mb = usage.free / (1024 * 1024)
        if free_mb < min_mb:
            logger.warning(
                f"Low disk space: {free_mb:.0f} MB free (minimum {min_mb} MB required)"
            )
            return False
        return True
    except Exception as exc:
        logger.warning(f"Disk space check failed (assuming OK): {exc}")
        return True

