"""TraceLit — Sessions API Router.

Session CRUD — list, create, get with history, rename, delete.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.api_schemas import (
    SessionCreateRequest,
    SessionSchema,
    SessionUpdateRequest,
)

router = APIRouter()


@router.get("/sessions", response_model=List[SessionSchema])
async def list_sessions(db: Session = Depends(get_db)) -> List[SessionSchema]:
    """List all sessions."""
    # TODO: Implement in Week 2+
    return []


@router.post("/sessions", response_model=SessionSchema, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Create a new analysis session."""
    # TODO: Implement in Week 2+
    raise NotImplementedError("Session creation not yet implemented")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    """Get session details with message history."""
    # TODO: Implement in Week 2+
    return {"id": session_id, "messages": []}


@router.patch("/sessions/{session_id}", response_model=SessionSchema)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Rename a session."""
    # TODO: Implement in Week 2+
    raise NotImplementedError("Session update not yet implemented")


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a session and its messages."""
    # TODO: Implement in Week 2+
    pass
