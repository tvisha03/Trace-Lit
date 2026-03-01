from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.crud.session_crud import (
    create_session,
    get_session,
    list_sessions,
    rename_session,
    delete_session as db_delete_session,
)
from infrastructure.db.crud.message_crud import delete_messages_by_session
from infrastructure.db.crud.paper_crud import get_papers_by_session
from infrastructure.db.crud.chunk_crud import delete_chunks_by_paper
from infrastructure.storage.file_storage import FileStorage
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.errors import NotFoundError
from shared.logger import get_logger

logger = get_logger(__name__)


async def create_new_session(
    db: AsyncSession,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a new research session. Returns session data dict."""
    session = await create_session(
        db,
        title=title or "New Session",
        description=description,
    )
    return {
        "id": str(session.id),
        "title": session.title,
        "description": session.description,
        "created_at": session.created_at.isoformat(),
    }


async def get_session_detail(db: AsyncSession, session_id: str) -> dict:
    """Fetch a session by ID. Raises NotFoundError if missing."""
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    return {
        "id": str(session.id),
        "title": session.title,
        "description": session.description,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def list_all_sessions(db: AsyncSession) -> list[dict]:
    """Return all sessions ordered by most recently updated."""
    sessions = await list_sessions(db)
    return [
        {
            "id": str(s.id),
            "title": s.title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


async def update_session_title(db: AsyncSession, session_id: str, new_title: str) -> dict:
    """Rename a session."""
    session = await rename_session(db, session_id, new_title)
    if not session:
        raise NotFoundError("Session", session_id)
    return {
        "id": str(session.id),
        "title": session.title,
        "description": session.description,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def delete_full_session(
    db: AsyncSession,
    session_id: str,
    faiss_store: FAISSStore,
    file_storage: FileStorage,
) -> bool:
    """
    Delete a session and all associated data: papers, chunks, vectors, files, messages.
    """
    papers = await get_papers_by_session(db, session_id)
    for paper in papers:
        faiss_store.remove_paper(str(paper.id))
        await delete_chunks_by_paper(db, str(paper.id))

    faiss_store.save()
    await delete_messages_by_session(db, session_id)
    file_storage.delete_session_uploads(session_id)
    file_storage.delete_session_exports(session_id)

    deleted = await db_delete_session(db, session_id)
    if not deleted:
        raise NotFoundError("Session", session_id)

    logger.info(f"Deleted session {session_id} with {len(papers)} papers")
    return True
