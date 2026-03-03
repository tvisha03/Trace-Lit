from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.crud.session_crud import (
    create_session,
    get_session,
    list_sessions,
    rename_session,
    delete_session as db_delete_session,
)
from infrastructure.db.crud.message_crud import delete_messages_by_session
from infrastructure.db.crud.paper_crud import get_papers_by_session, delete_paper
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
) -> list[str]:
    """Delete a session and all its related data in top-down order.

    Returns the list of paper IDs that were deleted so the caller can emit
    WebSocket events in the correct top-down sequence without the service
    layer needing to know about the WS infrastructure.
    """
    papers = await get_papers_by_session(db, session_id)
    paper_ids = [str(p.id) for p in papers]

    # Remove FAISS vectors, DB chunks, and paper records for every paper in
    # the session.  Explicit paper deletion provides defence-in-depth on top
    # of the ondelete="CASCADE" FK — SQLite only honours cascading deletes
    # when PRAGMA foreign_keys is ON (HI-005 fix).
    for paper in papers:
        faiss_store.remove_paper(str(paper.id))
        await delete_chunks_by_paper(db, str(paper.id))
        await delete_paper(db, str(paper.id))

    await delete_messages_by_session(db, session_id)

    deleted = await db_delete_session(db, session_id)
    if not deleted:
        raise NotFoundError("Session", session_id)

    # Commit all DB deletions atomically before touching the filesystem so the
    # database remains the authoritative source of truth if a later step fails.
    await db.commit()

    # Persist the trimmed FAISS index and remove uploaded/exported files only
    # after the DB transaction is committed successfully.
    faiss_store.save()
    file_storage.delete_session_uploads(session_id)
    file_storage.delete_session_exports(session_id)

    logger.info(f"Deleted session {session_id} with {len(papers)} papers")
    return paper_ids
