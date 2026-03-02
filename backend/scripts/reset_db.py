"""
reset_db.py – Drop and recreate the TraceLit SQLite schema.

Run this ONCE after pulling changes that add new FK constraints to the models
(e.g. the cascade-delete migration).  All existing data will be erased.

Usage:
    cd backend
    python scripts/reset_db.py
"""
import asyncio
import sys
from pathlib import Path

# Allow imports from the backend root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.db.database import engine, Base


async def reset() -> None:
    # Guard against accidental runs in non-interactive environments.
    answer = input(
        "\n⚠️  This will DROP all tables and recreate them.\n"
        "   All existing data (sessions, papers, messages, chunks) will be lost.\n"
        "   Continue? [y/N] "
    ).strip().lower()

    if answer != "y":
        print("Aborted.")
        return

    # Import all models so their metadata is registered before drop/create.
    from infrastructure.db.models import Paper, Chunk, Session, Message  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    print("✅  Schema recreated with FK cascade constraints.")


if __name__ == "__main__":
    asyncio.run(reset())
