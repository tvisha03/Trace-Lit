
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.message import Message

async def create_message(db: AsyncSession, **kwargs) -> Message:
    msg = Message(**kwargs)
    db.add(msg)
    await db.flush()
    return msg

async def get_messages_by_session(
    db: AsyncSession, session_id: str, limit: int | None = None
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    if limit:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def get_recent_messages(
    db: AsyncSession, session_id: str, max_turns: int = 5
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(max_turns * 2)
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()
    return messages

async def delete_messages_by_session(db: AsyncSession, session_id: str) -> None:
    msgs = await get_messages_by_session(db, session_id)
    for m in msgs:
        await db.delete(m)
    await db.flush()
