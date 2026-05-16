import asyncio
import sys
import os

sys.path.append(os.path.dirname(__file__))

from infrastructure.db.database import async_session_factory
from infrastructure.db.crud.message_crud import get_messages_by_session

async def main():
    async with async_session_factory() as db:
        # pyrefly: ignore [missing-import]
        from sqlalchemy import select
        from infrastructure.db.models.message import Message
        stmt = select(Message).order_by(Message.created_at.desc()).limit(1)
        res = await db.execute(stmt)
        msg = res.scalar_one_or_none()
        if msg and msg.havf_results:
            print("Citation ref:", msg.havf_results[0].get("citation_ref"))
            print("Transformation type:", msg.havf_results[0].get("transformation_type"))

if __name__ == "__main__":
    asyncio.run(main())
