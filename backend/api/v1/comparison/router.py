"""TraceLit — v1 Comparison Router.

Endpoints for generating, retrieving, and editing paper comparison tables.
Uses LLM extraction to populate structured contribution data per paper.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.v1.schemas import ComparisonUpdateRequest
from app.dependencies import get_db

router = APIRouter()


@router.get("/compare/{session_id}")
async def get_comparison(session_id: str, db: Session = Depends(get_db)):
    """Get existing comparison data for a session.

    Returns comparison rows if previously generated, otherwise empty.
    """
    from services.comparison_service import get_comparison_for_session

    try:
        result = await get_comparison_for_session(session_id, db)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/compare/{session_id}/generate")
async def generate_comparison(session_id: str, db: Session = Depends(get_db)):
    """Generate comparison table via LLM extraction.

    Extracts structured contributions (problem, method, dataset, metrics,
    results) from each paper in the session using LLM, stores them in the
    database, and returns the comparison table.
    """
    from services.comparison_service import generate_comparison_for_session

    try:
        result = await generate_comparison_for_session(session_id, db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/compare/{session_id}")
async def update_comparison(
    session_id: str,
    request: ComparisonUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update a single cell in the comparison table.

    Allows manual editing of auto-generated comparison data.
    """
    from services.comparison_service import update_comparison_cell

    try:
        result = await update_comparison_cell(
            session_id=session_id,
            paper_id=request.paper_id,
            field=request.field,
            value=request.value,
            db=db,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
