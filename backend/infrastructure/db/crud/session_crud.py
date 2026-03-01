"""TraceLit — Session CRUD operations."""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DBSession

from infrastructure.db.models.session import Session


def get_session(db: DBSession, session_id: str) -> Optional[Session]:
    return db.query(Session).filter(Session.id == session_id).first()


def get_all_sessions(db: DBSession) -> List[Session]:
    return db.query(Session).order_by(Session.updated_at.desc()).all()


def create_session(db: DBSession, session: Session) -> Session:
    db.add(session)
    db.flush()
    return session


def update_session_name(db: DBSession, session_id: str, name: str) -> Optional[Session]:
    session = get_session(db, session_id)
    if session:
        session.name = name
        session.updated_at = datetime.utcnow()
        db.flush()
    return session


def touch_session(db: DBSession, session_id: str) -> None:
    """Update the updated_at timestamp."""
    session = get_session(db, session_id)
    if session:
        session.updated_at = datetime.utcnow()
        db.flush()


def delete_session(db: DBSession, session_id: str) -> None:
    session = get_session(db, session_id)
    if session:
        db.delete(session)
