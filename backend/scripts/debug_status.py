"""Check DB status values and ORM query behavior."""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from infrastructure.db.database import async_session_factory
from sqlalchemy import text

async def check():
    async with async_session_factory() as db:
        r = await db.execute(text("SELECT DISTINCT status, typeof(status) FROM papers"))
        rows = r.fetchall()
        print("Distinct statuses in DB:")
        for row in rows:
            print(f"  value={row[0]!r} type={row[1]}")

        from infrastructure.db.crud.paper_crud import get_papers_by_session
        from shared.enums import PaperStatus
        print(f"\nPaperStatus.COMPLETED.value = {PaperStatus.COMPLETED.value!r}")
        print(f"PaperStatus.COMPLETED.name = {PaperStatus.COMPLETED.name!r}")

        papers = await get_papers_by_session(
            db, "13dac798-4080-4be8-b2b7-2d5c983070ea", status=PaperStatus.COMPLETED
        )
        print(f"\nORM query result: {len(papers)} papers")
        for p in papers:
            print(f"  id={p.id[:8]}.. status={p.status!r} file={p.filename}")

asyncio.run(check())
