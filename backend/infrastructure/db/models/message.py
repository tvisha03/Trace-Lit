"""TraceLit — Message ORM model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from infrastructure.db.database import Base


class Message(Base):
    """Chat message in a session (user or assistant)."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True)           # UUID
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"))
    role = Column(String)                           # "user" | "assistant"
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata_ = Column("metadata", Text)            # JSON: {confidence, sources, provider, ...}
