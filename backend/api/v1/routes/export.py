
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ExportRequest, ComparisonExportRequest, ExportResponse
from app.dependencies import get_db
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.storage.file_storage import FileStorage
from services.export_service import export_chat, export_comparison
from services.comparison_service import compare_papers
from shared.enums import ExportFormat

router = APIRouter()

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.post("", response_model=ExportResponse)
async def export_session(
    session_id: str,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
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
    llm = _get_llm(request)
    file_storage = FileStorage()
    fmt = ExportFormat(body.format)

    comparison_result = await compare_papers(body.paper_ids, db, llm)

    output_path = await export_comparison(
        session_id=session_id,
        comparison_content=comparison_result["comparison"],
        paper_titles=comparison_result["paper_titles"],
        export_format=fmt,
        file_storage=file_storage,
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
):
    file_storage = FileStorage()
    file_path = file_storage.get_export_path(filename, session_id)

    if not file_path.exists():
        from shared.errors import NotFoundError
        raise NotFoundError("Export file", filename)

    media_type = "application/pdf" if filename.endswith(".pdf") else \
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )
