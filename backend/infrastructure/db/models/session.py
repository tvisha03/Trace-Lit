"""TraceLit — Session ORM model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from infrastructure.db.database import Base


class Session(Base):
    """User analysis session grouping papers and conversation."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)           # UUID
    name = Column(String, default="Untitled Session")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paper_ids = Column(Text)                        # JSON array of paper UUIDs
