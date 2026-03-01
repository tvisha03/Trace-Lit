"""TraceLit — SQLAlchemy ORM Models.

All database tables for papers, sections, paragraphs, sessions, messages,
and contributions (comparison table).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.models.database import Base


class Paper(Base):
    """Uploaded research paper metadata."""

    __tablename__ = "papers"

    id = Column(String, primary_key=True)  # UUID
    title = Column(String, nullable=False)
    authors = Column(Text)  # JSON array: ["Author 1", "Author 2"]
    year = Column(Integer)
    pages = Column(Integer)
    file_path = Column(String)  # Path to stored PDF
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing")  # processing | ready | failed
    error_message = Column(Text)  # Error details if status == "failed"
    keywords = Column(Text)  # JSON array (Phase 2)
    summary = Column(Text)  # On-demand summary (Phase 2)


class Section(Base):
    """Detected section within a paper (e.g., Introduction, Methods)."""

    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"))
    title = Column(String)
    page_start = Column(Integer)
    order = Column(Integer)


class Paragraph(Base):
    """Individual paragraph with sentence-level tracking.

    The sentences column stores a JSON array:
    [{sentence_id: "P0_S0", text: "...", start_char: 0, end_char: 50}]
    """

    __tablename__ = "paragraphs"

    id = Column(String, primary_key=True)  # P0, P1, P2, ...
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"))
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"))
    text = Column(Text)
    page = Column(Integer)
    token_count = Column(Integer)
    embedding_id = Column(String)  # ChromaDB reference
    sentences = Column(Text)  # JSON: [{sentence_id, text, start_char, end_char}]


class Session(Base):
    """User analysis session grouping papers and conversation."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, default="Untitled Session")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paper_ids = Column(Text)  # JSON array of paper UUIDs


class Message(Base):
    """Chat message in a session (user or assistant)."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True)  # UUID
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"))
    role = Column(String)  # "user" | "assistant"
    content = Column(Text)  # Raw text / markdown
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata_ = Column("metadata", Text)  # JSON: {confidence, sources, provider, sentences[]}


class Contribution(Base):
    """Structured comparison table entry per paper.

    Each field has a source paragraph_id for traceability.
    """

    __tablename__ = "contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id", ondelete="CASCADE"), unique=True)
    problem = Column(Text)
    problem_source = Column(String)  # paragraph_id
    method = Column(Text)
    method_source = Column(String)
    dataset = Column(Text)
    dataset_source = Column(String)
    metrics = Column(Text)
    metrics_source = Column(String)
    results = Column(Text)
    results_source = Column(String)
