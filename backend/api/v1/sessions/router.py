"""TraceLit — v1 Sessions Router.

Session CRUD: list, create, get with history, rename, delete.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from api.v1.schemas import SessionCreateRequest, SessionSchema, SessionUpdateRequest
from app.dependencies import get_db
from infrastructure.db.models.message import Message
from infrastructure.db.models.session import Session as SessionModel

router = APIRouter()


# ============================================================
# Helper
# ============================================================

def _session_to_schema(session: SessionModel) -> SessionSchema:
    paper_ids: List[str] = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            paper_ids = []

    return SessionSchema(
        id=session.id,
        name=session.name or "Untitled Session",
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        paper_ids=paper_ids,
    )


# ============================================================
# Endpoints
# ============================================================

@router.get("/sessions", response_model=List[SessionSchema])
async def list_sessions(db: Session = Depends(get_db)) -> List[SessionSchema]:
    """List all sessions ordered by most recently updated."""
    sessions = (
        db.query(SessionModel)
        .order_by(SessionModel.updated_at.desc())
        .all()
    )
    return [_session_to_schema(s) for s in sessions]


@router.post("/sessions", response_model=SessionSchema, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Create a new analysis session."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    session = SessionModel(
        id=session_id,
        name=request.name or "Untitled Session",
        created_at=now,
        updated_at=now,
        paper_ids=json.dumps(request.paper_ids) if request.paper_ids else "[]",
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    logger.info("Session created: {} ({})", session_id, session.name)
    return _session_to_schema(session)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get session metadata with full message history."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
        .all()
    )

    message_list = []
    for msg in messages:
        meta: Dict = {}
        if msg.metadata_:
            try:
                meta = json.loads(msg.metadata_)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        message_list.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
            "metadata": meta,
        })

    schema = _session_to_schema(session)
    return {
        "id": schema.id,
        "name": schema.name,
        "created_at": schema.created_at,
        "updated_at": schema.updated_at,
        "paper_ids": schema.paper_ids,
        "messages": message_list,
    }


@router.patch("/sessions/{session_id}", response_model=SessionSchema)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    db: Session = Depends(get_db),
) -> SessionSchema:
    """Rename a session."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    session.name = request.name
    session.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(session)

    logger.info("Session renamed: {} → {}", session_id, request.name)
    return _session_to_schema(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a session and all its messages."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(session)
    db.commit()

    logger.info("Session deleted: {}", session_id)
