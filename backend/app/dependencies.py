from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_queue import SmartPaperQueue

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

def get_faiss_store(request: Request) -> FAISSStore:
    return request.app.state.faiss_store

def get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

def get_paper_queue(request: Request) -> SmartPaperQueue:
    return request.app.state.paper_queue

