
from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession

import asyncio
import hashlib
import time

from api.v1.schemas import PaperResponse, PaperListResponse, PaperUploadResponse
from api.v1.routes.websocket import ws_manager
from app.dependencies import get_db, get_faiss_store
from app.config import get_settings
from infrastructure.db.crud.paper_crud import get_paper as db_get_paper, get_paper_by_content_hash
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from infrastructure.db.database import async_session_factory
from services.paper_service import register_paper, get_session_papers, delete_paper
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

_TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED"})
_BATCH_WATCH_INTERVAL_SECONDS: float = 5.0

def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_upload_locks:
        _evict_idle_session_locks()
        _session_upload_locks[session_id] = asyncio.Lock()
    return _session_upload_locks[session_id]

def _evict_idle_session_locks() -> None:
    idle = [sid for sid, lock in _session_upload_locks.items() if not lock.locked()]
    for sid in idle:
        del _session_upload_locks[sid]

async def _validate_upload_preconditions(
    session_id: str, files: list[UploadFile], db: AsyncSession,
) -> None:
    settings = get_settings()
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    if len(files) > settings.MAX_UPLOAD_FILES:
        raise FileValidationError(f"Maximum {settings.MAX_UPLOAD_FILES} files allowed per upload")
    if not check_disk_space():
        raise TraceLitError(
            message="Insufficient disk space to accept new uploads. "
                    "Please free up storage and try again.",
            status_code=507,
        )

async def _validate_session_capacity(
    session_id: str, files: list[UploadFile], db: AsyncSession,
) -> set[str]:
    settings = get_settings()
    existing_papers = await get_session_papers(db, session_id)
    if len(existing_papers) + len(files) > settings.MAX_PAPERS_PER_SESSION:
        allowed = settings.MAX_PAPERS_PER_SESSION - len(existing_papers)
        raise FileValidationError(
            f"Session already has {len(existing_papers)} paper(s). "
            f"Maximum {settings.MAX_PAPERS_PER_SESSION} papers per session; "
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
    settings = get_settings()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    while True:
        chunk = await upload_file.read(1024 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise FileValidationError(
                f"{upload_file.filename} exceeds {settings.MAX_FILE_SIZE_MB}MB limit "
                f"({total_bytes / (1024 * 1024):.1f}MB+)"
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    if not content[:5].startswith(b"%PDF-"):
        raise FileValidationError(
            f"{upload_file.filename} is not a valid PDF file "
            "(missing %PDF- header). Please upload a genuine PDF document."
        )

    # --- Detect UTF-8 text-mode corruption ---
    # When a binary file is read as UTF-8 text (e.g. by Postman Desktop),
    # every byte > 0x7F gets replaced with the 3-byte U+FFFD sequence
    # (0xEF 0xBF 0xBD).  The %PDF- header survives because it's ASCII,
    # but all compressed streams are destroyed.  Detect this early.
    _UFFFD = b"\xef\xbf\xbd"
    probe = content[:2048]
    ufffd_hits = probe.count(_UFFFD)
    if ufffd_hits > 5:
        logger.error(
            f"UTF-8 text-mode corruption detected for "
            f"{upload_file.filename}: {ufffd_hits} U+FFFD replacements "
            f"in the first 2KB of upload data. The upload client is "
            f"reading the binary PDF as UTF-8 text before sending it."
        )
        raise FileValidationError(
            f"'{upload_file.filename}' was corrupted during upload — the "
            f"binary PDF data was read as text (UTF-8) by your upload "
            f"client, destroying all non-ASCII bytes. This is a known "
            f"issue with some versions of Postman Desktop on macOS.\n\n"
            f"SOLUTIONS (try in order):\n"
            f"  1. Use curl instead:\n"
            f"     curl -X POST "
            f"http://localhost:8000/api/v1/sessions/{{SESSION_ID}}/papers "
            f'-F "files=@/path/to/{upload_file.filename}"\n'
            f"  2. In Postman: ensure the form-data field type for 'files' "
            f"is 'File' (not 'Text')\n"
            f"  3. Try Postman Web (browser) or Insomnia instead of "
            f"Postman Desktop\n"
            f"  4. Re-select the file in Postman to force a fresh read"
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

def _sanitize_filename(raw_name: str | None) -> str:
    """Extract just the filename from a possibly-absolute path.

    Postman Desktop can send the full filesystem path (e.g.
    '/Users/foo/Downloads/paper.pdf') as the filename in the
    multipart Content-Disposition header.  We must strip it to
    the basename so that we never store or operate on the
    original user file.
    """
    import os

    if not raw_name:
        return f"upload_{hash(raw_name)}.pdf"
    # PureWindowsPath handles both / and \ separators
    from pathlib import PurePosixPath, PureWindowsPath

    name = PureWindowsPath(raw_name).name or PurePosixPath(raw_name).name or raw_name
    # Final safety: strip any remaining path separators
    return os.path.basename(name)


def _validate_saved_pdf(file_path, content_len: int, filename: str) -> None:
    """Open the freshly-saved PDF with pymupdf to catch corrupt uploads early.

    This runs *before* the file is enqueued for background processing,
    giving the caller an immediate 400 instead of a silent FAILED status.

    Checks:
    1. File size matches the uploaded content length.
    2. pymupdf can open the PDF and find at least one page.
    3. At least one of the first few pages yields extractable text OR
       a non-blank page render.  PDFs with universally-corrupted zlib
       content streams are rejected immediately rather than being sent
       to the slow processing queue where they will inevitably fail.
    """
    import pymupdf

    on_disk_size = file_path.stat().st_size
    logger.info(
        f"Post-save validation: {filename} — "
        f"content_len={content_len:,}, on_disk={on_disk_size:,}"
    )
    if on_disk_size != content_len:
        raise FileValidationError(
            f"{filename}: written file size ({on_disk_size:,}) differs from "
            f"upload content ({content_len:,}). The upload may be corrupted."
        )

    try:
        doc = pymupdf.open(str(file_path))
        if doc.is_encrypted:
            doc.authenticate("")
        page_count = len(doc)
    except Exception as exc:
        raise FileValidationError(
            f"{filename} could not be parsed as a valid PDF after saving: {exc}"
        )

    if page_count == 0:
        doc.close()
        try:
            raw = file_path.read_bytes()
            logger.error(
                f"ZERO-PAGE PDF detected after save: {filename}, "
                f"size={on_disk_size:,}, header={raw[:30]!r}, "
                f"tail={raw[-30:]!r}"
            )
        except Exception:
            pass
        raise FileValidationError(
            f"{filename} was saved successfully ({on_disk_size:,} bytes) but "
            f"contains 0 readable pages. The file may be corrupted or not a "
            f"genuine PDF. Please re-download it from the original source."
        )

    # Probe a sample of pages for extractable content (text or non-blank
    # render).  Catches PDFs whose zlib content streams are corrupted —
    # they contain valid page objects but decompress to nothing, causing
    # all three extraction tiers (layout, plain-text, OCR) to fail.
    _check_content_streams(doc, filename, page_count)
    doc.close()

    logger.info(f"Post-save validation passed: {filename}, {page_count} pages")


def _check_content_streams(doc, filename: str, page_count: int) -> None:
    """Reject PDFs whose content streams are universally corrupted.

    Samples up to 3 pages.  For each sampled page we first try text
    extraction; if that yields nothing we render at low DPI and check
    whether ANY pixel differs from pure white.  If every sampled page
    is blank by both measures the PDF is unusable and we fail fast.
    """
    sample_indices = list(range(min(3, page_count)))
    has_content = False

    for idx in sample_indices:
        page = doc[idx]

        # Fast check: does get_text() return anything?
        text = (page.get_text("text") or "").strip()
        if len(text) >= 20:
            has_content = True
            break

        # Slow check: does the page render any non-white pixels?
        pix = page.get_pixmap(dpi=36)  # very low DPI for speed
        samples = pix.samples
        if any(b != 255 for b in samples):
            has_content = True
            break

    if not has_content:
        doc.close()
        logger.error(
            f"Content-stream corruption detected for {filename}: "
            f"sampled {len(sample_indices)} page(s), all blank "
            f"(0 text, all-white render). The PDF's internal "
            f"compressed streams appear to be damaged."
        )
        raise FileValidationError(
            f"'{filename}' appears to have corrupted internal content — "
            f"all sampled pages are completely blank (no extractable text "
            f"and no visible content when rendered). This usually means "
            f"the PDF file was corrupted during upload transfer (e.g. "
            f"the upload client read binary data as UTF-8 text). "
            f"Try uploading via curl:\n"
            f"  curl -X POST "
            f"http://localhost:8000/api/v1/sessions/{{SESSION_ID}}/papers "
            f'-F "files=@/path/to/{filename}"'
        )


async def _register_paper(
    content: bytes,
    upload_file: UploadFile,
    content_hash: str,
    session_id: str,
    db: AsyncSession,
    file_storage: FileStorage,
) -> str:
    safe_filename = _sanitize_filename(upload_file.filename)
    size_mb = len(content) / (1024 * 1024)
    file_path = file_storage.save_upload(content, safe_filename, session_id)

    # Catch corrupt/invalid PDFs immediately instead of letting them
    # fail silently in the background processing queue.
    _validate_saved_pdf(file_path, len(content), safe_filename)

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
    async with async_session_factory() as check_db:
        paper = await db_get_paper(check_db, paper_id)
    if not paper:
        return ""
    status = paper.status
    return status.value if hasattr(status, "value") else str(status)

async def _all_papers_terminal(paper_ids: list[str]) -> tuple[bool, int, int]:
    statuses = [await _paper_status_str(pid) for pid in paper_ids]
    if not all(s in _TERMINAL_STATUSES for s in statuses if s):
        return False, 0, 0
    completed = sum(1 for s in statuses if s == "COMPLETED")
    return True, completed, len(paper_ids) - completed

async def _check_batch_terminal(paper_ids: list[str]) -> tuple[bool, int, int]:
    try:
        return await _all_papers_terminal(paper_ids)
    except Exception as exc:
        logger.warning(f"Error checking batch terminal status: {exc}")
        return False, 0, 0

async def _watch_batch_completion(
    paper_ids: list[str],
    session_id: str,
) -> None:
    deadline = time.monotonic() + get_settings().PAPER_PROCESSING_TIMEOUT_SECONDS + 60.0
    while time.monotonic() < deadline:
        await asyncio.sleep(_BATCH_WATCH_INTERVAL_SECONDS)
        done, completed, failed = await _check_batch_terminal(paper_ids)
        if done:
            await _send_batch_complete_event(session_id, paper_ids, completed, failed)
            return
    logger.warning(
        f"Batch completion watch timed out for session {session_id} "
        f"after {get_settings().PAPER_PROCESSING_TIMEOUT_SECONDS + 60:.0f}s"
    )

async def _send_batch_complete_event(
    session_id: str,
    paper_ids: list[str],
    completed: int,
    failed: int,
) -> None:
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
    files: list[UploadFile] = File(
        ...,
        description="One or more PDF files to upload",
        media_type="application/pdf",
    ),
    db: AsyncSession = Depends(get_db),
):
    _upload_limiter.enforce(request)
    await _validate_upload_preconditions(session_id, files, db)

    session_lock = _get_session_lock(session_id)
    async with session_lock:
        await _validate_session_capacity(session_id, files, db)
        file_storage = FileStorage()
        paper_ids = await _register_all_papers(files, session_id, db, file_storage)

    if not session_lock.locked():
        _session_upload_locks.pop(session_id, None)

    paper_queue = request.app.state.paper_queue
    for pid in paper_ids:
        await paper_queue.enqueue(pid, session_id)

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

