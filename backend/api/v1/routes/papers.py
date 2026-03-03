
from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession

import asyncio
import hashlib

from api.v1.schemas import PaperResponse, PaperListResponse, PaperUploadResponse
from api.v1.routes.websocket import ws_manager
from app.dependencies import get_db, get_faiss_store
from infrastructure.db.crud.paper_crud import get_paper as db_get_paper, get_paper_by_content_hash
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from services.paper_service import register_paper, get_session_papers, delete_paper, mark_paper_failed
from shared.constants import MAX_UPLOAD_FILES, MAX_FILE_SIZE_MB, MAX_PAPERS_PER_SESSION
from shared.errors import FileValidationError, ForbiddenError, NotFoundError, TraceLitError
from shared.utils.rate_limiter import SlidingWindowRateLimiter
from shared.utils.file_utils import check_disk_space
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


async def _register_and_enqueue(
    content: bytes,
    upload_file: UploadFile,
    content_hash: str,
    session_id: str,
    db: AsyncSession,
    file_storage: FileStorage,
    paper_queue,
) -> str:
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

    try:
        await paper_queue.enqueue(paper_id, session_id)
    except Exception as enqueue_exc:
        logger.error(f"Failed to enqueue paper {paper_id}: {enqueue_exc}")
        await mark_paper_failed(
            db, paper_id, reason=f"Processing queue unavailable: {enqueue_exc}"
        )
        raise TraceLitError(
            message=f"Processing queue unavailable for '{upload_file.filename}'. "
                    "Please try again later.",
            status_code=503,
        )
    return paper_id


async def _process_uploads(
    files: list[UploadFile],
    session_id: str,
    db: AsyncSession,
    file_storage: FileStorage,
    paper_queue,
) -> list[str]:
    paper_ids = []
    for upload_file in files:
        content, content_hash = await _read_and_validate_file(
            upload_file, session_id, db,
        )
        paper_id = await _register_and_enqueue(
            content, upload_file, content_hash,
            session_id, db, file_storage, paper_queue,
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
        paper_queue = request.app.state.paper_queue
        paper_ids = await _process_uploads(files, session_id, db, file_storage, paper_queue)

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

