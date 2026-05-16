from fastapi import APIRouter, Depends, Path, Request, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ExportRequest, ComparisonExportRequest, ExportResponse, ExportListItem, ExportListResponse
from app.dependencies import get_db
from infrastructure.db.crud.session_crud import get_session
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.storage.file_storage import FileStorage
from services.export_service import export_chat, export_comparison
from services.comparison_service import compare_papers, extract_paper_contributions
from shared.enums import ExportFormat
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

@router.get("", response_model=ExportListResponse)
async def list_exports(session_id: str):
    """List all export files currently available for download in this session.

    Use the returned ``filename`` values with the
    ``GET /export/download/{filename}`` endpoint.
    Note: each file is deleted from disk once it has been downloaded.
    """
    file_storage = FileStorage()
    files = file_storage.list_exports(session_id)
    items = [
        ExportListItem(
            filename=f.name,
            download_url=f"/api/v1/sessions/{session_id}/export/download/{f.name}",
            size_bytes=f.stat().st_size,
        )
        for f in files
    ]
    return ExportListResponse(exports=items)


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

async def _validate_paper_ownership(paper_ids: list[str], session_id: str, db: AsyncSession) -> None:
    for pid in paper_ids:
        paper = await get_paper(db, pid)
        if not paper or str(paper.session_id) != session_id:
            raise NotFoundError("Paper", pid)

async def _gather_contributions(
    paper_ids: list[str], db: AsyncSession, llm: FallbackChain,
) -> list[dict]:
    contributions: list[dict] = []
    for pid in paper_ids:
        try:
            contributions.append(await extract_paper_contributions(pid, db, llm))
        except Exception as exc:
            logger.warning(f"Contribution extraction failed for {pid}: {exc}")
            contributions.append({"paper_id": pid, "contributions": {}})
    return contributions

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

    await _validate_paper_ownership(body.paper_ids, session_id, db)

    llm = _get_llm(request)
    file_storage = FileStorage()
    fmt = ExportFormat(body.format)

    comparison_result = await compare_papers(body.paper_ids, db, llm)

    contributions = (
        await _gather_contributions(body.paper_ids, db, llm)
        if fmt == ExportFormat.EXCEL else None
    )

    output_path = await export_comparison(
        session_id=session_id,
        comparison_content=comparison_result["comparison"],
        paper_titles=comparison_result["paper_titles"],
        export_format=fmt,
        file_storage=file_storage,
        paper_ids=body.paper_ids,
        db=db,
        contributions=contributions,
        comparison_table=comparison_result.get("comparison_table"),
    )

    return ExportResponse(
        download_url=f"/api/v1/sessions/{session_id}/export/download/{output_path.name}",
        filename=output_path.name,
        format=body.format,
    )

@router.get("/download/{filename}")
async def download_export(
    session_id: str,
    filename: Annotated[
        str,
        Path(
            description=(
                "Exact filename returned by the POST /export or POST /export/comparison "
                "endpoint (e.g. 'chat_0ef9e115_ab12cd.pdf'). "
                "Use GET /export to list files that are currently available for download."
            )
        ),
    ],
    background_tasks: BackgroundTasks,
):
    _validate_filename(filename)

    file_storage = FileStorage()
    file_path = file_storage.get_export_path(filename, session_id)

    # If the file isn't under the requested session, check all sessions.
    # This happens when the user copies a filename but the download URL
    # references a different session than the one used during export.
    if not file_path.exists():
        found = file_storage.find_export(filename)
        if found is not None:
            logger.info(
                f"Export '{filename}' not found under session {session_id!r} — "
                f"resolved via cross-session search to {found}"
            )
            file_path = found

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

