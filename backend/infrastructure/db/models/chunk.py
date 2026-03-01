"""
Chunk — paragraph-level chunk with sentence boundary map.
Enriched text is stored for embedding; original text for display.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    paper_id: Mapped[str] = mapped_column(String(36), index=True)
    paragraph_id: Mapped[str] = mapped_column(String(32))  # e.g. "P5"
    text: Mapped[str] = mapped_column(Text)  # original text for display
    enriched_text: Mapped[str] = mapped_column(Text)  # [Paper][Section] prefixed — for embedding
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentence_map: Mapped[dict] = mapped_column(JSON, default=dict)
    # sentence_map schema: {"P5_S0": {"text": "...", "start": 0, "end": 45, "tokens": 11}, ...}
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
