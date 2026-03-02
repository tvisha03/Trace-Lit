
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.paper import Paper
from shared.enums import PaperStatus

async def create_paper(db: AsyncSession, **kwargs) -> Paper:
    paper = Paper(**kwargs)
    db.add(paper)
    await db.flush()
    return paper

async def get_paper(db: AsyncSession, paper_id: str) -> Paper | None:
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    return result.scalar_one_or_none()

async def get_papers_by_session(
    db: AsyncSession, session_id: str, status: PaperStatus | None = None
) -> list[Paper]:
    stmt = select(Paper).where(Paper.session_id == session_id)
    if status:
        stmt = stmt.where(Paper.status == status)
    stmt = stmt.order_by(Paper.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def update_paper_status(
    db: AsyncSession,
    paper_id: str,
    status: PaperStatus,
    progress: float = 0.0,
    **extra_fields,
) -> None:
    values: dict = {"status": status, "progress": progress, **extra_fields}
    await db.execute(update(Paper).where(Paper.id == paper_id).values(**values))
    await db.flush()

async def get_stuck_papers(db: AsyncSession) -> list[Paper]:
    terminal = {PaperStatus.COMPLETED, PaperStatus.FAILED}
    stuck_statuses = [s for s in PaperStatus if s not in terminal]
    stmt = select(Paper).where(Paper.status.in_(stuck_statuses))
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def delete_paper(db: AsyncSession, paper_id: str) -> None:
    paper = await get_paper(db, paper_id)
    if paper:
        await db.delete(paper)
        await db.flush()
