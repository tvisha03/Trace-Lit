"""TraceLit — Message CRUD operations."""

import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from infrastructure.db.models.message import Message


def get_messages_for_session(db: Session, session_id: str) -> List[Message]:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
        .all()
    )


def create_message(
    db: Session,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict] = None,
) -> Message:
    msg = Message(
        id=message_id,
        session_id=session_id,
        role=role,
        content=content,
        timestamp=datetime.utcnow(),
        metadata_=json.dumps(metadata) if metadata else None,
    )
    db.add(msg)
    db.flush()
    return msg


def delete_messages_for_session(db: Session, session_id: str) -> None:
    db.query(Message).filter(Message.session_id == session_id).delete()
