"""
Paper upload and management routes.
"""

from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import PaperResponse, PaperListResponse, PaperUploadResponse
from app.dependencies import get_db, get_faiss_store
from infrastructure.storage.file_storage import FileStorage
from services.paper_service import register_paper, get_session_papers, delete_paper
from shared.constants import MAX_UPLOAD_FILES, MAX_FILE_SIZE_MB
from shared.errors import FileValidationError
from shared.utils.file_utils import get_file_size_mb
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("", response_model=PaperUploadResponse, status_code=201)
async def upload_papers(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload 1–7 PDF files to a session.
    Files are validated (type, size) then queued for processing.
    """
    if len(files) > MAX_UPLOAD_FILES:
        raise FileValidationError(f"Maximum {MAX_UPLOAD_FILES} files allowed per upload")

    file_storage = FileStorage()
    paper_ids = []

    for upload_file in files:
        # Validate file type
        if not upload_file.filename or not upload_file.filename.lower().endswith(".pdf"):
            raise FileValidationError(f"Only PDF files are accepted: {upload_file.filename}")

        # Validate file size
        content = await upload_file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise FileValidationError(
                f"{upload_file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit ({size_mb:.1f}MB)"
            )

        # Save to disk
        file_path = file_storage.save_upload(content, upload_file.filename, session_id)

        # Register in DB
        paper_id = await register_paper(
            db,
            session_id=session_id,
            filename=upload_file.filename,
            file_path=str(file_path),
            file_size_mb=round(size_mb, 2),
        )
        paper_ids.append(paper_id)

        # Enqueue for processing
        paper_queue = request.app.state.paper_queue
        await paper_queue.enqueue(paper_id, session_id)

    return PaperUploadResponse(
        paper_ids=paper_ids,
        message=f"{len(paper_ids)} paper(s) uploaded and queued for processing",
    )


@router.get("", response_model=PaperListResponse)
async def list_papers(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all papers in a session."""
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
    """Get a single paper's details."""
    from infrastructure.db.crud.paper_crud import get_paper as db_get_paper
    paper = await db_get_paper(db, paper_id)
    if not paper:
        from shared.errors import NotFoundError
        raise NotFoundError("Paper", paper_id)

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
    """Delete a paper and its associated chunks/vectors."""
    await delete_paper(paper_id, db, faiss_store)
