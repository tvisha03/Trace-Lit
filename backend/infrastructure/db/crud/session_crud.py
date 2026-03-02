
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.session import Session

async def create_session(db: AsyncSession, **kwargs) -> Session:
    session_obj = Session(**kwargs)
    db.add(session_obj)
    await db.flush()
    return session_obj

async def get_session(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()

async def list_sessions(db: AsyncSession) -> list[Session]:
    result = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    return list(result.scalars().all())

async def rename_session(db: AsyncSession, session_id: str, title: str) -> Session | None:
    session_obj = await get_session(db, session_id)
    if not session_obj:
        return None
    session_obj.title = title
    await db.flush()
    await db.refresh(session_obj)
    return session_obj

async def delete_session(db: AsyncSession, session_id: str) -> bool:
    session_obj = await get_session(db, session_id)
    if session_obj:
        await db.delete(session_obj)
        await db.flush()
        return True
    return False
