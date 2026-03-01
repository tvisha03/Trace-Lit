"""TraceLit — Paper, Section, and Contribution ORM models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from infrastructure.db.database import Base


class Paper(Base):
    """Uploaded research paper metadata."""

    __tablename__ = "papers"

    id = Column(String, primary_key=True)          # UUID
    title = Column(String, nullable=False)
    authors = Column(Text)                          # JSON array: ["Author 1", ...]
    year = Column(Integer)
    pages = Column(Integer)
    file_path = Column(String)
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing")  # processing | ready | failed
    error_message = Column(Text)
    keywords = Column(Text)                         # JSON array (Phase 2)
    summary = Column(Text)                          # On-demand summary (Phase 2)


class Section(Base):
    """Detected section within a paper."""

    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"))
    title = Column(String)
    page_start = Column(Integer)
    order = Column(Integer)


class Contribution(Base):
    """Structured comparison table entry per paper.

    Each text field has a source paragraph_id for full traceability.
    """

    __tablename__ = "contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"), unique=True)
    problem = Column(Text)
    problem_source = Column(String)
    method = Column(Text)
    method_source = Column(String)
    dataset = Column(Text)
    dataset_source = Column(String)
    metrics = Column(Text)
    metrics_source = Column(String)
    results = Column(Text)
    results_source = Column(String)
