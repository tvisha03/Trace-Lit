"""TraceLit — Export API Router.

PDF and Excel export endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.api_schemas import ExportRequest

router = APIRouter()


@router.post("/export/pdf")
async def export_pdf(request: ExportRequest, db: Session = Depends(get_db)):
    """Export session to PDF via WeasyPrint + Jinja2."""
    # TODO: Implement in Week 7
    raise NotImplementedError("PDF export not yet implemented")


@router.post("/export/excel")
async def export_excel(request: ExportRequest, db: Session = Depends(get_db)):
    """Export comparison table to Excel."""
    # TODO: Implement in Week 7
    raise NotImplementedError("Excel export not yet implemented")
