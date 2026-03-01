"""TraceLit — Session Service (Business Logic).

Thin facade over session CRUD — used by both v1 and legacy routers.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session as DBSession

from api.v1.schemas import SessionCreateRequest, SessionSchema, SessionUpdateRequest
from infrastructure.db.models.message import Message
from infrastructure.db.models.session import Session as SessionModel


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


async def list_sessions(db: DBSession) -> List[SessionSchema]:
    sessions = (
        db.query(SessionModel)
        .order_by(SessionModel.updated_at.desc())
        .all()
    )
    return [_session_to_schema(s) for s in sessions]


async def create_session(request: SessionCreateRequest, db: DBSession) -> SessionSchema:
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


async def get_session_with_history(
    session_id: str,
    db: DBSession,
) -> Optional[Dict[str, Any]]:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        return None

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


async def rename_session(
    session_id: str,
    request: SessionUpdateRequest,
    db: DBSession,
) -> Optional[SessionSchema]:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        return None

    session.name = request.name
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    logger.info("Session renamed: {} → {}", session_id, request.name)
    return _session_to_schema(session)


async def delete_session(session_id: str, db: DBSession) -> bool:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        return False
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    logger.info("Session deleted: {}", session_id)
    return True
