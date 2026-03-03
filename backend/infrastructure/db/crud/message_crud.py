
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.message import Message

async def create_message(db: AsyncSession, **kwargs) -> Message:
    msg = Message(**kwargs)
    db.add(msg)
    await db.flush()
    return msg

async def get_messages_by_session(
    db: AsyncSession,
    session_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Message]:
    """Retrieve messages for a session, ordered by creation time ascending.

    Supports optional ``limit`` and ``offset`` for pagination.
    """
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def count_messages_by_session(
    db: AsyncSession, session_id: str,
) -> int:
    """Return the total number of messages in a session (for pagination metadata)."""
    stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
    result = await db.execute(stmt)
    return result.scalar_one()

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
    """Delete all messages for a session in a single SQL statement.

    Uses a bulk DELETE instead of loading-then-deleting each row individually
    to avoid O(N) roundtrips on sessions with many messages.
    """
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(Message).where(Message.session_id == session_id))
    await db.flush()
