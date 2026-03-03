from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_queue import SmartPaperQueue

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for the request lifetime.

    BUG-9 fix: The session no longer auto-commits on yield exit.  Services
    are responsible for calling ``await session.commit()`` explicitly so each
    route can control its own transaction boundaries.  Auto-commit was causing
    double commits (once in the service, once here) which is harmless for
    SQLite but semantically incorrect and masks missing commits.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

def get_faiss_store(request: Request) -> FAISSStore:
    return request.app.state.faiss_store

def get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

def get_paper_queue(request: Request) -> SmartPaperQueue:
    return request.app.state.paper_queue
