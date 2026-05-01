import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.db.database import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class EvaluationCache(Base):
    __tablename__ = "evaluation_cache"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    query: Mapped[str] = mapped_column(String(512), index=True)
    paper_ids: Mapped[str] = mapped_column(Text)
    results: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
