
from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession

import asyncio
import hashlib
import time

from api.v1.schemas import PaperResponse, PaperListResponse, PaperUploadResponse
from api.v1.routes.websocket import ws_manager
from app.dependencies import get_db, get_faiss_store
from infrastructure.db.crud.paper_crud import get_paper as db_get_paper, get_paper_by_content_hash
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from infrastructure.db.database import async_session_factory
from services.paper_service import register_paper, get_session_papers, delete_paper
from shared.constants import (
    MAX_UPLOAD_FILES,
    MAX_FILE_SIZE_MB,
    MAX_PAPERS_PER_SESSION,
    PAPER_PROCESSING_TIMEOUT_SECONDS,
)
from shared.errors import FileValidationError, ForbiddenError, NotFoundError, TraceLitError
from shared.enums import PaperStatus
from shared.utils.rate_limiter import SlidingWindowRateLimiter
from shared.utils.file_utils import check_disk_space
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_upload_limiter = SlidingWindowRateLimiter(
    max_calls=5, window_seconds=60.0, resource_name="upload requests",
)

_session_upload_locks: dict[str, asyncio.Lock] = {}

# Terminal paper states — a batch is done when every paper reaches one of these.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED"})
# Poll interval for the batch-completion watcher.
_BATCH_WATCH_INTERVAL_SECONDS: float = 5.0


def _get_session_lock(session_id: str) -> asyncio.Lock:
    """Return (or create) the per-session upload lock.

    Idle locks are pruned on creation to prevent the dict from growing
    indefinitely across thousands of sessions (Bug-3 fix).
    """
    if session_id not in _session_upload_locks:
        # Evict any unlocked entries before adding a new one.
        _evict_idle_session_locks()
        _session_upload_locks[session_id] = asyncio.Lock()
    return _session_upload_locks[session_id]


def _evict_idle_session_locks() -> None:
    """Remove entries whose locks are no longer held.

    Because asyncio is single-threaded, checking ``lock.locked()`` here is
    race-free: no other coroutine can acquire or release a lock between the
    check and the deletion.
    """
    idle = [sid for sid, lock in _session_upload_locks.items() if not lock.locked()]
    for sid in idle:
        del _session_upload_locks[sid]


async def _validate_upload_preconditions(
    session_id: str, files: list[UploadFile], db: AsyncSession,
) -> None:
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    if len(files) > MAX_UPLOAD_FILES:
        raise FileValidationError(f"Maximum {MAX_UPLOAD_FILES} files allowed per upload")
    if not check_disk_space():
        raise TraceLitError(
            message="Insufficient disk space to accept new uploads. "
                    "Please free up storage and try again.",
            status_code=507,
        )


async def _validate_session_capacity(
    session_id: str, files: list[UploadFile], db: AsyncSession,
) -> set[str]:
    from pathlib import Path as _Path

    existing_papers = await get_session_papers(db, session_id)
    # Only count non-failed papers toward capacity and duplicate checks.
    # Failed papers have no file on disk; users should be able to retry.
    active_papers = [p for p in existing_papers if p.status != PaperStatus.FAILED]
    if len(active_papers) + len(files) > MAX_PAPERS_PER_SESSION:
        allowed = MAX_PAPERS_PER_SESSION - len(active_papers)
        raise FileValidationError(
            f"Session already has {len(active_papers)} paper(s). "
            f"Maximum {MAX_PAPERS_PER_SESSION} papers per session; "
            f"you can upload at most {max(0, allowed)} more."
        )
    existing_filenames = {p.filename for p in active_papers}
    # Compare basenames only — some clients send full filesystem paths
    incoming_filenames = [_Path(f.filename).name for f in files if f.filename]
    duplicates = [fn for fn in incoming_filenames if fn in existing_filenames]
    if duplicates:
        dup_list = ", ".join(duplicates[:5])
        raise FileValidationError(
            f"Duplicate file(s) already exist in this session: {dup_list}. "
            "Please rename the file or remove the existing paper first."
        )
    return existing_filenames


async def _read_and_validate_file(
    upload_file: UploadFile, session_id: str, db: AsyncSession,
) -> tuple[bytes, str]:
    if not upload_file.filename or not upload_file.filename.lower().endswith(".pdf"):
        raise FileValidationError(f"Only PDF files are accepted: {upload_file.filename}")

    chunks: list[bytes] = []
    total_bytes = 0
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    while True:
        chunk = await upload_file.read(1024 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise FileValidationError(
                f"{upload_file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit "
                f"({total_bytes / (1024 * 1024):.1f}MB+)"
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    if not content[:5].startswith(b"%PDF-"):
        raise FileValidationError(
            f"{upload_file.filename} is not a valid PDF file "
            "(missing %PDF- header). Please upload a genuine PDF document."
        )

    content_hash = hashlib.sha256(content).hexdigest()
    existing = await get_paper_by_content_hash(db, session_id, content_hash)
    if existing:
        raise FileValidationError(
            f"'{upload_file.filename}' is identical in content to an "
            f"already-uploaded paper ('{existing.filename}'). "
            "Please remove the existing paper first if you want to re-upload."
        )
    return content, content_hash


async def _register_paper(
    content: bytes,
    upload_file: UploadFile,
    content_hash: str,
    session_id: str,
    db: AsyncSession,
    file_storage: FileStorage,
) -> str:
    """Save file and register paper record in DB. Does not start processing."""
    from pathlib import Path as _Path

    size_mb = len(content) / (1024 * 1024)
    file_path = file_storage.save_upload(content, upload_file.filename, session_id)
    # Use the basename so the DB record never stores a raw client-side path
    safe_filename = _Path(upload_file.filename).name

    paper_id = await register_paper(
        db,
        session_id=session_id,
        filename=safe_filename,
        file_path=str(file_path),
        file_size_mb=round(size_mb, 2),
        content_hash=content_hash,
    )
    return paper_id


async def _paper_status_str(paper_id: str) -> str:
    """Return the status string for a paper, or empty string if not found."""
    async with async_session_factory() as check_db:
        paper = await db_get_paper(check_db, paper_id)
    if not paper:
        return ""
    status = paper.status
    return status.value if hasattr(status, "value") else str(status)


async def _all_papers_terminal(paper_ids: list[str]) -> tuple[bool, int, int]:
    """Check whether every paper in *paper_ids* has reached a terminal state.

    Returns ``(all_done, completed_count, failed_count)``.  Uses a fresh
    DB session per call so long-lived polling doesn't hold a connection open.
    """
    statuses = [await _paper_status_str(pid) for pid in paper_ids]
    if not all(s in _TERMINAL_STATUSES for s in statuses if s):
        return False, 0, 0
    completed = sum(1 for s in statuses if s == "COMPLETED")
    return True, completed, len(paper_ids) - completed


async def _check_batch_terminal(paper_ids: list[str]) -> tuple[bool, int, int]:
    """Safely check batch terminal status; return (done, completed, failed).

    Catches exceptions and logs them; returns (False, 0, 0) on error so
    polling continues rather than crashing.
    """
    try:
        return await _all_papers_terminal(paper_ids)
    except Exception as exc:
        logger.warning(f"Error checking batch terminal status: {exc}")
        return False, 0, 0


async def _watch_batch_completion(
    paper_ids: list[str],
    session_id: str,
) -> None:
    """Poll paper DB status; emit ``upload_batch_complete`` once all reach a terminal state.

    This replaces the previous asyncio.gather-based approach that ran processing
    directly in the route.  Processing now happens inside SmartPaperQueue; this
    task only watches for completion and emits the summary WS event.
    """
    deadline = time.monotonic() + PAPER_PROCESSING_TIMEOUT_SECONDS + 60.0
    while time.monotonic() < deadline:
        await asyncio.sleep(_BATCH_WATCH_INTERVAL_SECONDS)
        done, completed, failed = await _check_batch_terminal(paper_ids)
        if done:
            await _send_batch_complete_event(session_id, paper_ids, completed, failed)
            return
    logger.warning(
        f"Batch completion watch timed out for session {session_id} "
        f"after {PAPER_PROCESSING_TIMEOUT_SECONDS + 60:.0f}s"
    )


async def _send_batch_complete_event(
    session_id: str,
    paper_ids: list[str],
    completed: int,
    failed: int,
) -> None:
    """Emit upload_batch_complete WebSocket event."""
    try:
        await ws_manager.send_event(
            session_id=session_id,
            event_type="upload_batch_complete",
            data={
                "paper_ids": paper_ids,
                "total": len(paper_ids),
                "completed": completed,
                "failed": failed,
            },
        )
    except Exception as ws_exc:
        logger.warning(f"WS upload_batch_complete failed for session {session_id}: {ws_exc}")


async def _register_all_papers(
    files: list[UploadFile],
    session_id: str,
    db: AsyncSession,
    file_storage: FileStorage,
) -> list[str]:
    """Read, validate, and register every uploaded file; return list of paper IDs."""
    paper_ids: list[str] = []
    for upload_file in files:
        content, content_hash = await _read_and_validate_file(
            upload_file, session_id, db,
        )
        paper_id = await _register_paper(
            content, upload_file, content_hash,
            session_id, db, file_storage,
        )
        paper_ids.append(paper_id)
    return paper_ids


@router.post("", response_model=PaperUploadResponse, status_code=201)
async def upload_papers(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    _upload_limiter.enforce(request)
    await _validate_upload_preconditions(session_id, files, db)

    session_lock = _get_session_lock(session_id)
    async with session_lock:
        await _validate_session_capacity(session_id, files, db)
        file_storage = FileStorage()
        # Register all papers first (fast: DB write + file save only)
        paper_ids = await _register_all_papers(files, session_id, db, file_storage)

    # Release the lock entry from the dict now that the critical section is done.
    # If no other upload for this session is waiting the entry is stale.
    if not session_lock.locked():
        _session_upload_locks.pop(session_id, None)

    # Bug-2 fix: enqueue to SmartPaperQueue instead of running a local semaphore.
    # The queue handles concurrency, memory pressure checks, timeout, and graceful
    # shutdown — previously this route duplicated all of that logic.
    paper_queue = request.app.state.paper_queue
    for pid in paper_ids:
        await paper_queue.enqueue(pid, session_id)

    # Watch in the background: emit upload_batch_complete when all papers finish.
    asyncio.create_task(_watch_batch_completion(paper_ids, session_id))

    return PaperUploadResponse(
        paper_ids=paper_ids,
        message=f"{len(paper_ids)} paper(s) uploaded and queued for processing",
    )

@router.get("", response_model=PaperListResponse)
async def list_papers(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_session_papers(db, session_id)
    items = [
        PaperResponse(
            id=str(p.id),
            session_id=str(p.session_id),
            filename=p.filename,
            title=p.title,
            authors=p.authors,
            year=p.year,
            abstract=p.abstract,
            doi=p.doi,
            status=p.status.value if hasattr(p.status, "value") else p.status,
            progress=p.progress or 0.0,
            page_count=p.page_count,
            chunk_count=p.chunk_count,
            file_size_mb=p.file_size_mb,
            error_message=p.error_message,
            created_at=p.created_at.isoformat(),
        )
        for p in papers
    ]
    return PaperListResponse(papers=items)

@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    session_id: str,
    paper_id: str,
    db: AsyncSession = Depends(get_db),
):
    paper = await db_get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    return PaperResponse(
        id=str(paper.id),
        session_id=str(paper.session_id),
        filename=paper.filename,
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        abstract=paper.abstract,
        doi=paper.doi,
        status=paper.status.value if hasattr(paper.status, "value") else paper.status,
        progress=paper.progress or 0.0,
        page_count=paper.page_count,
        chunk_count=paper.chunk_count,
        file_size_mb=paper.file_size_mb,
        error_message=paper.error_message,
        created_at=paper.created_at.isoformat(),
    )

def _get_paper_status(paper) -> str:
    return paper.status.value if hasattr(paper.status, "value") else paper.status


def _is_paper_processing(paper) -> bool:
    _processing_statuses = {"EXTRACTING", "CHUNKING", "EMBEDDING", "QUEUED"}
    return _get_paper_status(paper) in _processing_statuses


async def _validate_paper_and_permissions(
    db: AsyncSession,
    paper_id: str,
    session_id: str,
    request: Request,
) -> None:
    paper = await db_get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)
    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    if not _is_paper_processing(paper):
        return

    paper_queue = getattr(request.app.state, "paper_queue", None)
    if paper_queue and paper_id in paper_queue._active_jobs:
        raise TraceLitError(
            message=f"Paper '{paper_id}' is currently being processed and cannot be deleted. "
                    "Please wait for processing to complete or fail before deleting.",
            status_code=409,
        )


async def _broadcast_deletion(paper_id: str, session_id: str) -> None:
    try:
        await ws_manager.send_event(
            session_id,
            "paper_deleted",
            {"paper_id": paper_id, "session_id": session_id},
        )
    except Exception as exc:
        logger.warning(f"WS paper_deleted event failed for {paper_id}: {exc}")


async def _perform_deletion(
    paper_id: str,
    db: AsyncSession,
    faiss_store,
    session_id: str,
) -> None:
    deleted = await delete_paper(paper_id, db, faiss_store)
    if not deleted:
        raise NotFoundError("Paper", paper_id)
    await db.commit()
    await _broadcast_deletion(paper_id, session_id)


@router.delete("/{paper_id}", status_code=204)
async def remove_paper(
    session_id: str,
    paper_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    await _validate_paper_and_permissions(db, paper_id, session_id, request)
    await _perform_deletion(paper_id, db, faiss_store, session_id)

