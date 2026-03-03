
from collections import defaultdict
from time import monotonic

from fastapi import APIRouter, Depends, UploadFile, File, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import PaperResponse, PaperListResponse, PaperUploadResponse
from api.v1.routes.websocket import ws_manager
from app.dependencies import get_db, get_faiss_store
from infrastructure.db.crud.paper_crud import get_paper as db_get_paper
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from services.paper_service import register_paper, get_session_papers, delete_paper, mark_paper_failed
from shared.constants import MAX_UPLOAD_FILES, MAX_FILE_SIZE_MB
from shared.errors import FileValidationError, ForbiddenError, NotFoundError
from shared.utils.file_utils import get_file_size_mb
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Sliding-window rate limiter for the paper upload endpoint.
# Uploading triggers expensive PDF extraction, chunking, and embedding, so we
# cap each client IP to _UPLOAD_RATE_LIMIT_MAX batches per window to prevent
# resource exhaustion from rapid-fire uploads.
#
# ⚠️  PRODUCTION NOTE (HI-001): This is an in-memory implementation and is
# therefore NOT suitable for multi-instance / multi-worker deployments.  In
# those environments counters are not shared between processes, so the window
# can be exceeded by a factor equal to the worker count.  Migrate to a
# Redis-backed or database-backed rate limiter before scaling horizontally.
# ---------------------------------------------------------------------------
_UPLOAD_RATE_LIMIT_MAX = 5
_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = 60.0
_upload_rate_limit_calls: dict[str, list[float]] = defaultdict(list)


def _enforce_upload_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    cutoff = now - _UPLOAD_RATE_LIMIT_WINDOW_SECONDS

    calls = _upload_rate_limit_calls[client_ip]
    _upload_rate_limit_calls[client_ip] = [t for t in calls if t > cutoff]

    if len(_upload_rate_limit_calls[client_ip]) >= _UPLOAD_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {_UPLOAD_RATE_LIMIT_MAX} upload "
                f"requests per {int(_UPLOAD_RATE_LIMIT_WINDOW_SECONDS)} seconds."
            ),
        )

    _upload_rate_limit_calls[client_ip].append(now)

@router.post("", response_model=PaperUploadResponse, status_code=201)
async def upload_papers(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    _enforce_upload_rate_limit(request)

    # CRT-002/BUG-001: Validate that the target session exists before creating
    # any paper records.  Without this check a user could register papers under
    # a non-existent session_id, causing FK violations or orphaned data.
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    if len(files) > MAX_UPLOAD_FILES:
        raise FileValidationError(f"Maximum {MAX_UPLOAD_FILES} files allowed per upload")

    file_storage = FileStorage()
    paper_ids = []

    for upload_file in files:
        if not upload_file.filename or not upload_file.filename.lower().endswith(".pdf"):
            raise FileValidationError(f"Only PDF files are accepted: {upload_file.filename}")

        content = await upload_file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise FileValidationError(
                f"{upload_file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit ({size_mb:.1f}MB)"
            )

        file_path = file_storage.save_upload(content, upload_file.filename, session_id)

        paper_id = await register_paper(
            db,
            session_id=session_id,
            filename=upload_file.filename,
            file_path=str(file_path),
            file_size_mb=round(size_mb, 2),
        )
        paper_ids.append(paper_id)

        paper_queue = request.app.state.paper_queue
        try:
            await paper_queue.enqueue(paper_id, session_id)
        except Exception as enqueue_exc:
            # Paper was successfully registered in DB but failed to enter the
            # processing queue.  Mark it FAILED immediately so it is not left
            # stranded in REGISTERED state with no worker ever picking it up.
            logger.error(f"Failed to enqueue paper {paper_id}: {enqueue_exc}")
            await mark_paper_failed(
                db, paper_id, reason=f"Processing queue unavailable: {enqueue_exc}"
            )
            raise HTTPException(
                status_code=503,
                detail=f"Processing queue unavailable for '{upload_file.filename}'. "
                       "Please try again later.",
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
    # Return a structured 404 instead of an empty list when the session does
    # not exist so clients can distinguish 'session has no papers' from 'session
    # never existed'.
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

    # CRT-003: Validate ownership — a paper retrieved by ID must belong to the
    # provided session to prevent cross-session data exposure.
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

@router.delete("/{paper_id}", status_code=204)
async def remove_paper(
    session_id: str,
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    # MINOR-001/CRT-004: Verify the paper exists AND belongs to the caller's
    # session before deletion so that a user cannot remove another session's
    # papers by guessing paper IDs.
    paper = await db_get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)
    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    deleted = await delete_paper(paper_id, db, faiss_store)
    if not deleted:
        raise NotFoundError("Paper", paper_id)
    await db.commit()

    # Notify all connections in the session that this paper has been removed.
    # Fire after the commit so the client only reacts to confirmed deletions.
    try:
        await ws_manager.send_event(
            session_id,
            "paper_deleted",
            {"paper_id": paper_id, "session_id": session_id},
        )
    except Exception as exc:
        logger.warning(f"WS paper_deleted event failed for {paper_id}: {exc}")

    return None
