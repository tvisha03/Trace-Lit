
from sqlalchemy import insert, select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.chunk import Chunk

async def create_chunks_bulk(db: AsyncSession, chunks: list[dict]) -> int:
    if not chunks:
        return 0
    await db.execute(insert(Chunk), chunks)
    return len(chunks)

async def get_chunks_by_paper(db: AsyncSession, paper_id: str) -> list[Chunk]:
    result = await db.execute(
        select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.paragraph_id)
    )
    return list(result.scalars().all())

async def get_chunk_by_paragraph_id(
    db: AsyncSession, paper_id: str, paragraph_id: str
) -> Chunk | None:
    result = await db.execute(
        select(Chunk).where(
            Chunk.paper_id == paper_id, Chunk.paragraph_id == paragraph_id
        )
    )
    return result.scalar_one_or_none()

async def get_chunks_by_ids(db: AsyncSession, chunk_ids: list[str]) -> list[Chunk]:
    result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    return list(result.scalars().all())

async def delete_chunks_by_paper(db: AsyncSession, paper_id: str) -> None:
    await db.execute(sa_delete(Chunk).where(Chunk.paper_id == paper_id))
    await db.flush()

async def get_chunks_by_papers(db: AsyncSession, paper_ids: list[str]) -> dict[str, list[Chunk]]:
    if not paper_ids:
        return {}

    result = await db.execute(
        select(Chunk).where(Chunk.paper_id.in_(paper_ids)).order_by(Chunk.paper_id, Chunk.paragraph_id)
    )
    chunks = list(result.scalars().all())

    chunks_by_paper: dict[str, list[Chunk]] = {pid: [] for pid in paper_ids}
    for chunk in chunks:
        chunks_by_paper[str(chunk.paper_id)].append(chunk)

    return chunks_by_paper

