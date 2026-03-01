"""TraceLit — v1 Sessions Router.

Thin router: delegates all business logic to services.session_service.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.v1.schemas import SessionCreateRequest, SessionSchema, SessionUpdateRequest
from app.dependencies import get_db

router = APIRouter()


@router.get("/sessions", response_model=List[SessionSchema])
async def list_sessions(db: Session = Depends(get_db)) -> List[SessionSchema]:
    """List all sessions ordered by most recently updated."""
    from services.session_service import list_sessions as svc_list
    return await svc_list(db)


@router.post("/sessions", response_model=SessionSchema, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Create a new analysis session."""
    from services.session_service import create_session as svc_create
    return await svc_create(request, db)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get session metadata with full message history."""
    from services.session_service import get_session_with_history
    result = await get_session_with_history(session_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return result


@router.patch("/sessions/{session_id}", response_model=SessionSchema)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Rename a session."""
    from services.session_service import rename_session
    result = await rename_session(session_id, request, db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return result


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a session and all its messages."""
    from services.session_service import delete_session as svc_delete
    deleted = await svc_delete(session_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
