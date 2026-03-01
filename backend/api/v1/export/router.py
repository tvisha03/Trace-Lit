"""TraceLit — v1 Export Router (Phase 2 stubs)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.v1.schemas import ExportRequest
from app.dependencies import get_db

router = APIRouter()


@router.post("/export/pdf")
async def export_pdf(request: ExportRequest, db: Session = Depends(get_db)):
    """Export session to PDF via WeasyPrint + Jinja2 (Phase 2)."""
    return {
        "status": "not_implemented",
        "detail": "PDF export is planned for Phase 2.",
    }


@router.post("/export/excel")
async def export_excel(request: ExportRequest, db: Session = Depends(get_db)):
    """Export comparison table to Excel (Phase 2)."""
    return {
        "status": "not_implemented",
        "detail": "Excel export is planned for Phase 2.",
    }
