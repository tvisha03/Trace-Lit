
import asyncio
import uuid

from infrastructure.db.database import init_db, async_session_factory
from infrastructure.db.crud.session_crud import create_session

async def seed():
    print("Initialising database...")
    await init_db()

    async with async_session_factory() as db:
        session_id = str(uuid.uuid4())
        session = await create_session(
            db,
            session_id=session_id,
            title="Demo Session",
            description="A pre-seeded session for development and testing.",
        )
        print(f"Created session: {session.id} — {session.title}")

    print("Database seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
