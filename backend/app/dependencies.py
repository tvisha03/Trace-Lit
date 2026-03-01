"""
FastAPI dependency injection functions.
Provides request-scoped database sessions and shared singletons.
"""

from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_queue import SmartPaperQueue


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional database session, auto-rolled-back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_faiss_store(request: Request) -> FAISSStore:
    """Retrieve the shared FAISS store attached to app state at startup."""
    return request.app.state.faiss_store


def get_llm(request: Request) -> FallbackChain:
    """Retrieve the shared LLM fallback chain attached at startup."""
    return request.app.state.llm


def get_paper_queue(request: Request) -> SmartPaperQueue:
    """Retrieve the shared paper processing queue attached at startup."""
    return request.app.state.paper_queue
