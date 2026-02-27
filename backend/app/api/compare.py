"""TraceLit — Comparison Table API Router.

Get, generate, and update comparison data for papers in a session.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db

router = APIRouter()


@router.get("/compare/{session_id}")
async def get_comparison(session_id: str, db: Session = Depends(get_db)):
    """Get existing comparison data for a session."""
    # TODO: Implement in Week 7
    return {"session_id": session_id, "contributions": []}


@router.post("/compare/{session_id}/generate")
async def generate_comparison(session_id: str, db: Session = Depends(get_db)):
    """Generate comparison table via LLM extraction."""
    # TODO: Implement in Week 7
    raise NotImplementedError("Comparison generation not yet implemented")


@router.patch("/compare/{session_id}")
async def update_comparison(session_id: str, db: Session = Depends(get_db)):
    """Update edited comparison table cells."""
    # TODO: Implement in Week 7
    raise NotImplementedError("Comparison update not yet implemented")
