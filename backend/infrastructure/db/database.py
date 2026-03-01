"""TraceLit — Database Engine & Session Management.

SQLite with WAL mode and foreign keys enabled.
Single writer with async-compatible session factory.
"""

from sqlalchemy import event, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite pragmas for performance and correctness."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI dependency — yields a database session, auto-closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they don't exist. Called at startup."""
    from infrastructure.db.models import Paper, Section, Paragraph, Session as SessionModel, Message, Contribution
    Base.metadata.create_all(bind=engine)
