
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
from services.paper_service import register_paper, get_session_papers, delete_paper, process_paper
from workers.paper_worker import _progress_to_stage
from shared.constants import (
    MAX_UPLOAD_FILES,
    MAX_FILE_SIZE_MB,
    MAX_PAPERS_PER_SESSION,
    MAX_PARALLEL_PAPERS,
    PAPER_PROCESSING_TIMEOUT_SECONDS,
)
from shared.errors import FileValidationError, ForbiddenError, NotFoundError, TraceLitError
from shared.utils.rate_limiter import SlidingWindowRateLimiter
from shared.utils.file_utils import check_disk_space
from shared.utils.memory_monitor import is_memory_pressure_high
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_upload_limiter = SlidingWindowRateLimiter(
    max_calls=5, window_seconds=60.0, resource_name="upload requests",
)

_session_upload_locks: dict[str, asyncio.Lock] = {}

def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_upload_locks:
        _session_upload_locks[session_id] = asyncio.Lock()
    return _session_upload_locks[session_id]


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
    existing_papers = await get_session_papers(db, session_id)
    if len(existing_papers) + len(files) > MAX_PAPERS_PER_SESSION:
        allowed = MAX_PAPERS_PER_SESSION - len(existing_papers)
        raise FileValidationError(
            f"Session already has {len(existing_papers)} paper(s). "
            f"Maximum {MAX_PAPERS_PER_SESSION} papers per session; "
            f"you can upload at most {max(0, allowed)} more."
        )
    existing_filenames = {p.filename for p in existing_papers}
    incoming_filenames = [f.filename for f in files if f.filename]
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
    size_mb = len(content) / (1024 * 1024)
    file_path = file_storage.save_upload(content, upload_file.filename, session_id)

    paper_id = await register_paper(
        db,
        session_id=session_id,
        filename=upload_file.filename,
        file_path=str(file_path),
        file_size_mb=round(size_mb, 2),
        content_hash=content_hash,
    )
    return paper_id


_MEMORY_BACKOFF_SECONDS: float = 1.0
_MAX_MEMORY_WAITS: int = 6


async def _wait_for_memory() -> None:
    """Pause before acquiring a processing slot when memory pressure is high."""
    for attempt in range(1, _MAX_MEMORY_WAITS + 1):
        if not is_memory_pressure_high():
            return
        logger.warning(
            f"Memory pressure high — delaying paper processing "
            f"(attempt {attempt}/{_MAX_MEMORY_WAITS})"
        )
        await asyncio.sleep(_MEMORY_BACKOFF_SECONDS)
    logger.warning("Max memory-pressure waits exceeded — proceeding anyway")


async def _process_single_paper(
    paper_id: str,
    session_id: str,
    faiss_store,
    llm_chain,
    semaphore: asyncio.Semaphore,
) -> None:
    """Process one paper with WS progress updates inside a concurrency semaphore.

    Checks memory pressure before acquiring the slot, mirrors the WS payload
    produced by paper_job_processor in the background queue worker.
    """
    start_time = time.monotonic()

    async def progress_callback(progress: float) -> None:
        try:
            stage = _progress_to_stage(progress)
            elapsed = time.monotonic() - start_time
            if progress < 0:
                eta_seconds = 0.0
            else:
                clamped = max(0.01, min(progress, 1.0))
                eta_seconds = 0.0 if clamped >= 1.0 else round(
                    elapsed * (1.0 - clamped) / clamped, 1
                )
            await ws_manager.send_event(
                session_id=session_id,
                event_type="paper_progress",
                data={
                    "paper_id": paper_id,
                    "progress": progress,
                    "stage": stage,
                    "eta_seconds": eta_seconds,
                },
            )
        except Exception as ws_exc:
            logger.warning(f"WS progress send failed for {paper_id}: {ws_exc}")

    # Wait for memory to settle before claiming a semaphore slot.
    await _wait_for_memory()

    async with semaphore:
        try:
            async with async_session_factory() as db:
                await asyncio.wait_for(
                    process_paper(
                        paper_id=paper_id,
                        db=db,
                        faiss_store=faiss_store,
                        progress_callback=progress_callback,
                        llm_chain=llm_chain,
                    ),
                    timeout=PAPER_PROCESSING_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            logger.error(
                f"Paper {paper_id} timed out after {PAPER_PROCESSING_TIMEOUT_SECONDS}s"
            )
        except Exception as exc:
            logger.error(f"Background processing failed for {paper_id}: {exc}")


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


async def _process_batch_background(
    paper_ids: list[str],
    session_id: str,
    faiss_store,
    llm_chain,
) -> None:
    """Background task: process all papers from an upload batch in parallel.

    Up to MAX_PARALLEL_PAPERS run concurrently; each waits for memory pressure
    to clear before starting. When every paper finishes (success or failure)
    an ``upload_batch_complete`` WebSocket event is sent so the client knows the
    full batch is done.
    """
    semaphore = asyncio.Semaphore(MAX_PARALLEL_PAPERS)
    results = await asyncio.gather(
        *[
            _process_single_paper(pid, session_id, faiss_store, llm_chain, semaphore)
            for pid in paper_ids
        ],
        return_exceptions=True,
    )

    # Count outcomes: None means success, anything else is an exception.
    failed = sum(1 for r in results if r is not None)
    completed = len(paper_ids) - failed

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
        logger.warning(f"WS upload_batch_complete send failed for session {session_id}: {ws_exc}")


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

    # Kick off background processing — returns immediately so 201 is sent to the client.
    # Progress is streamed via WebSocket; upload_batch_complete is emitted when done.
    asyncio.create_task(
        _process_batch_background(
            paper_ids,
            session_id,
            request.app.state.faiss_store,
            request.app.state.llm,
        )
    )

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

