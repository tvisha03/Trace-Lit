"""TraceLit — Paragraph / Chunk ORM model."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from infrastructure.db.database import Base


class Paragraph(Base):
    """Individual paragraph with sentence-level tracking.

    The ``sentences`` column stores a JSON array::

        [{"sentence_id": "P0_S0", "text": "...", "start_char": 0, "end_char": 50}]
    """

    __tablename__ = "paragraphs"

    id = Column(String, primary_key=True)           # e.g. "paper_uuid_P0"
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"))
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"))
    text = Column(Text)
    page = Column(Integer)
    token_count = Column(Integer)
    embedding_id = Column(String)                   # FAISS int64 id (as string)
    sentences = Column(Text)                        # JSON sentence map
