"""TraceLit — v1 Comparison Router (Phase 2 stubs)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db

router = APIRouter()


@router.get("/compare/{session_id}")
async def get_comparison(session_id: str, db: Session = Depends(get_db)):
    """Get existing comparison data for a session (Phase 2)."""
    return {"session_id": session_id, "contributions": []}


@router.post("/compare/{session_id}/generate")
async def generate_comparison(session_id: str, db: Session = Depends(get_db)):
    """Generate comparison table via LLM extraction (Phase 2)."""
    return {
        "status": "not_implemented",
        "detail": "Comparison generation is planned for Phase 2.",
    }


@router.patch("/compare/{session_id}")
async def update_comparison(session_id: str, db: Session = Depends(get_db)):
    """Update edited comparison table cells (Phase 2)."""
    return {
        "status": "not_implemented",
        "detail": "Comparison update is planned for Phase 2.",
    }
