
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.database import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Cascade: deleting a Paper removes all its Chunks at the DB level,
    # serving as a safety net alongside delete_chunks_by_paper in the service.
    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
    paragraph_id: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    enriched_text: Mapped[str] = mapped_column(Text)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentence_map: Mapped[dict] = mapped_column(JSON, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
