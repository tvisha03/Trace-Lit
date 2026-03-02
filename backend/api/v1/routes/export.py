
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

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.post("", response_model=ExportResponse)
async def export_session(
    session_id: str,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify the session exists before delegating to the export service so
    # callers receive a structured 404 rather than an opaque service-layer error.
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
    # Verify the session exists.
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    # Verify every requested paper belongs to this session so one session
    # cannot export data from another session's papers.
    for pid in body.paper_ids:
        paper = await get_paper(db, pid)
        if not paper:
            raise NotFoundError("Paper", pid)
        if str(paper.session_id) != session_id:
            raise NotFoundError("Paper", pid)  # intentionally opaque — not your paper

    llm = _get_llm(request)
    file_storage = FileStorage()
    fmt = ExportFormat(body.format)

    comparison_result = await compare_papers(body.paper_ids, db, llm)

    # Persist the comparison as an assistant message so users can review
    # previous comparisons via the session message history (CRT-005 fix).
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
    file_storage = FileStorage()
    file_path = file_storage.get_export_path(filename, session_id)

    if not file_path.exists():
        raise NotFoundError("Export file", filename)

    media_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "text/x-bibtex"
        if filename.endswith(".bib")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Schedule file deletion as a background task so it runs after the
    # FileResponse has been fully sent to the client, preventing disk
    # accumulation of one-time export files.
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
