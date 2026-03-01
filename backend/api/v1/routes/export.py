"""
Export routes — download chat or comparison as PDF / Excel.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ExportRequest, ExportResponse
from app.dependencies import get_db
from infrastructure.storage.file_storage import FileStorage
from services.export_service import export_chat
from workers.export_worker import run_export_in_thread
from shared.enums import ExportFormat

router = APIRouter()


@router.post("", response_model=ExportResponse)
async def export_session(
    session_id: str,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Export a chat session to PDF or Excel."""
    fmt = ExportFormat(body.format)
    file_storage = FileStorage()

    output_path = await export_chat(session_id, fmt, db, file_storage)

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
    """Download an exported file."""
    file_storage = FileStorage()
    file_path = file_storage.get_export_path(session_id, filename)

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
