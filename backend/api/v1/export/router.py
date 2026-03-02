"""TraceLit — v1 Export Router.

Endpoints for exporting sessions and comparison tables to PDF, Excel, and Word.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.v1.schemas import ExportRequest
from app.dependencies import get_db

router = APIRouter()


@router.post("/export/pdf")
async def export_pdf(request: ExportRequest, db: Session = Depends(get_db)):
    """Export session conversation to PDF.

    Generates a professional PDF with cover page, messages,
    citations, confidence indicators, and paper references.
    """
    from services.export_service import export_session_pdf

    try:
        output_path = await export_session_pdf(request.session_id, db)
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export/excel")
async def export_excel(request: ExportRequest, db: Session = Depends(get_db)):
    """Export comparison table to Excel.

    Generates an Excel workbook with comparison table, paper metadata,
    and export information sheets.
    """
    from services.export_service import export_comparison_excel

    try:
        output_path = await export_comparison_excel(request.session_id, db)
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export/session-excel")
async def export_session_excel(request: ExportRequest, db: Session = Depends(get_db)):
    """Export full session data (conversation + papers) to Excel."""
    from services.export_service import export_session_excel

    try:
        output_path = await export_session_excel(request.session_id, db)
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export/word")
async def export_word(request: ExportRequest, db: Session = Depends(get_db)):
    """Export session conversation to Word (DOCX).

    Generates a styled Word document with messages, citations as superscripts,
    and paper references.
    """
    from services.export_service import export_session_word

    try:
        output_path = await export_session_word(request.session_id, db)
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export/literature-review/word")
async def export_literature_review_word(request: ExportRequest, db: Session = Depends(get_db)):
    """Export literature review to Word (DOCX).

    Generates a styled Word document of the generated literature review
    for the given session's papers.
    """
    from services.export_service import export_literature_review_word

    try:
        output_path = await export_literature_review_word(request.session_id, db)
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
