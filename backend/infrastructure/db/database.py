from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

_SQLITE_BUSY_TIMEOUT_MS = settings.SQLITE_BUSY_TIMEOUT_MS  # FIXED MINOR-003: Now configurable via settings
_POOL_CHECKOUT_TIMEOUT_S = 60

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    # FIXED MED-005: Increased pool size for better concurrent request handling
    # Previous: pool_size=5, max_overflow=3 (max 8 connections)
    # Now: pool_size=10, max_overflow=5 (max 15 connections)
    pool_size=10,
    max_overflow=5,
    pool_timeout=_POOL_CHECKOUT_TIMEOUT_S,
    pool_recycle=1800,
    connect_args={"timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000, "check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS};")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
    finally:
        cursor.close()


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Auto-migrate: add sentence_embeddings column if missing (LAT-1 optimisation)
        await conn.run_sync(_migrate_sentence_embeddings_column)


def _migrate_sentence_embeddings_column(connection) -> None:
    """Add sentence_embeddings column to chunks table if it doesn't exist.

    Handles existing databases that were created before the LAT-1
    embedding cache optimisation was introduced.
    """
    from sqlalchemy import text, inspect

    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("chunks")]
    if "sentence_embeddings" not in columns:
        connection.execute(
            text("ALTER TABLE chunks ADD COLUMN sentence_embeddings BLOB")
        )

