
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ExportRequest, ComparisonExportRequest, ExportResponse
from app.dependencies import get_db
from infrastructure.db.crud.session_crud import get_session
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.message_crud import create_message
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.storage.file_storage import FileStorage
from services.export_service import export_chat, export_comparison
from services.comparison_service import compare_papers
from shared.enums import ExportFormat, MessageRole
from shared.errors import NotFoundError
from shared.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

def _get_media_type(filename: str) -> str:
    if filename.endswith(".pdf"):
        return "application/pdf"
    if filename.endswith(".bib"):
        return "text/x-bibtex"
    if filename.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if filename.endswith(".tex"):
        return "application/x-tex"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def _validate_filename(filename: str) -> None:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise NotFoundError("Export file", filename)

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.post("", response_model=ExportResponse)
async def export_session(
    session_id: str,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    fmt = ExportFormat(body.format)
    file_storage = FileStorage()

    output_path = await export_chat(session_id, fmt, db, file_storage)

    return ExportResponse(
        download_url=f"/api/v1/sessions/{session_id}/export/download/{output_path.name}",
        filename=output_path.name,
        format=body.format,
    )

@router.post("/comparison", response_model=ExportResponse)
async def export_comparison_route(
    session_id: str,
    body: ComparisonExportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    for pid in body.paper_ids:
        paper = await get_paper(db, pid)
        if not paper:
            raise NotFoundError("Paper", pid)
        if str(paper.session_id) != session_id:
            raise NotFoundError("Paper", pid)

    llm = _get_llm(request)
    file_storage = FileStorage()
    fmt = ExportFormat(body.format)

    comparison_result = await compare_papers(body.paper_ids, db, llm)

    await create_message(
        db,
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=comparison_result["comparison"],
        provider=comparison_result.get("provider"),
        havf_results=[],
    )
    await db.commit()

    output_path = await export_comparison(
        session_id=session_id,
        comparison_content=comparison_result["comparison"],
        paper_titles=comparison_result["paper_titles"],
        export_format=fmt,
        file_storage=file_storage,
        paper_ids=body.paper_ids,
        db=db,
    )

    return ExportResponse(
        download_url=f"/api/v1/sessions/{session_id}/export/download/{output_path.name}",
        filename=output_path.name,
        format=body.format,
    )

@router.get("/download/{filename}")
async def download_export(
    session_id: str,
    filename: str,
    background_tasks: BackgroundTasks,
):
    _validate_filename(filename)

    file_storage = FileStorage()
    file_path = file_storage.get_export_path(filename, session_id)

    try:
        file_path.resolve().relative_to(file_storage._exports.resolve())
    except ValueError:
        raise NotFoundError("Export file", filename)

    if not file_path.exists():
        raise NotFoundError("Export file", filename)

    media_type = _get_media_type(filename)

    def _delete_file() -> None:
        try:
            file_path.unlink(missing_ok=True)
            logger.info(f"Deleted export file after download: {file_path}")
        except Exception as exc:
            logger.warning(f"Could not delete export file {file_path}: {exc}")

    background_tasks.add_task(_delete_file)

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )

