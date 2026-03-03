
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, Text, Enum as SAEnum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.database import Base
from shared.enums import PaperStatus

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Cascade: deleting a Session removes all its Papers at the DB level,
    # serving as a safety net alongside the service-layer cleanup.
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authors: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(PaperStatus), default=PaperStatus.REGISTERED, index=True  # MED-005: explicit initial state
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    file_size_mb: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Composite index supports the common (session_id, status) filter used by
    # get_papers_by_session with a status argument in paper_service and routes.
    __table_args__ = (
        Index("ix_papers_session_status", "session_id", "status"),
    )
