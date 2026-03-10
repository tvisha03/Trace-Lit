
import shutil
from pathlib import Path
from typing import BinaryIO, Union

from app.config import get_settings
from shared.logger import get_logger

logger = get_logger(__name__)

class FileStorage:

    def __init__(self, uploads_dir: str | None = None, exports_dir: str | None = None) -> None:
        settings = get_settings()
        uploads_dir = uploads_dir or settings.UPLOADS_DIR
        exports_dir = exports_dir or settings.EXPORTS_DIR
        self._uploads = Path(uploads_dir)
        self._exports = Path(exports_dir)
        self._uploads.mkdir(parents=True, exist_ok=True)
        self._exports.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file: Union[BinaryIO, bytes], filename: str, session_id: str) -> Path:
        if isinstance(file, (bytes, bytearray, memoryview)):
            content: bytes = bytes(file)
        else:
            content = file.read()
        if not content:
            raise ValueError(f"File '{filename}' is empty; refusing to save.")
        dest_dir = self._uploads / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = (dest_dir / filename).resolve()
        try:
            dest.write_bytes(content)
        except OSError as exc:
            logger.error(f"Failed to write upload '{dest}': {exc}")
            raise
        if dest.stat().st_size != len(content):
            dest.unlink(missing_ok=True)
            raise OSError(f"Write verification failed for '{dest}': size mismatch.")
        logger.info(f"Saved upload: {dest}")
        return dest

    def get_upload_path(self, filename: str, session_id: str) -> Path:
        return (self._uploads / session_id / filename).resolve()

    def delete_session_uploads(self, session_id: str) -> None:
        session_dir = self._uploads / session_id
        if session_dir.is_dir():
            shutil.rmtree(session_dir)
            logger.info(f"Deleted uploads for session {session_id}")

    def save_export(self, content: bytes, filename: str, session_id: str) -> Path:
        dest_dir = self._exports / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = (dest_dir / filename).resolve()
        dest.write_bytes(content)
        logger.info(f"Saved export: {dest}")
        return dest

    def get_export_path(self, filename: str, session_id: str) -> Path:
        return (self._exports / session_id / filename).resolve()

    def find_export(self, filename: str) -> Path | None:
        """Search all session subdirectories for *filename*.

        Called when the download request carries a session_id that doesn't
        match where the file was actually saved (e.g. the user copied the
        filename but navigated to a different session URL).  Export filenames
        embed the originating session prefix and a random suffix so collisions
        are practically impossible.
        """
        exports_root = self._exports.resolve()
        if not exports_root.is_dir():
            return None
        for session_dir in exports_root.iterdir():
            if not session_dir.is_dir():
                continue
            candidate = session_dir / filename
            if candidate.exists():
                return candidate.resolve()
        return None

    def list_exports(self, session_id: str) -> list[Path]:
        """Return all export files that currently exist for *session_id*."""
        exports_dir = (self._exports / session_id).resolve()
        if not exports_dir.is_dir():
            return []
        return sorted(exports_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

    def delete_session_exports(self, session_id: str) -> None:
        exports_dir = self._exports / session_id
        if exports_dir.is_dir():
            shutil.rmtree(exports_dir)

