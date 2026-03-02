
import shutil
from pathlib import Path
from typing import BinaryIO

from shared.constants import UPLOADS_DIR, EXPORTS_DIR
from shared.logger import get_logger

logger = get_logger(__name__)

class FileStorage:

    def __init__(self, uploads_dir: str = UPLOADS_DIR, exports_dir: str = EXPORTS_DIR) -> None:
        self._uploads = Path(uploads_dir)
        self._exports = Path(exports_dir)
        self._uploads.mkdir(parents=True, exist_ok=True)
        self._exports.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file: BinaryIO, filename: str, session_id: str) -> Path:
        content = file if isinstance(file, bytes) else file.read()
        if not content:
            raise ValueError(f"File '{filename}' is empty; refusing to save.")
        dest_dir = self._uploads / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        try:
            dest.write_bytes(content)
        except OSError as exc:
            logger.error(f"Failed to write upload '{dest}': {exc}")
            raise
        # Verify the written file size matches what was provided
        if dest.stat().st_size != len(content):
            dest.unlink(missing_ok=True)
            raise OSError(f"Write verification failed for '{dest}': size mismatch.")
        logger.info(f"Saved upload: {dest}")
        return dest

    def get_upload_path(self, filename: str, session_id: str) -> Path:
        return self._uploads / session_id / filename

    def delete_session_uploads(self, session_id: str) -> None:
        session_dir = self._uploads / session_id
        if session_dir.is_dir():
            shutil.rmtree(session_dir)
            logger.info(f"Deleted uploads for session {session_id}")

    def save_export(self, content: bytes, filename: str, session_id: str) -> Path:
        dest_dir = self._exports / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        dest.write_bytes(content)
        logger.info(f"Saved export: {dest}")
        return dest

    def get_export_path(self, filename: str, session_id: str) -> Path:
        return self._exports / session_id / filename

    def delete_session_exports(self, session_id: str) -> None:
        exports_dir = self._exports / session_id
        if exports_dir.is_dir():
            shutil.rmtree(exports_dir)
