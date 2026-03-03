"""CRUD layer — public API for database operations.

Re-exports all CRUD functions so callers can do::

    from infrastructure.db.crud import get_paper, create_session, ...
"""

from infrastructure.db.crud.paper_crud import (
    create_paper,
    get_paper,
    get_papers_by_session,
    update_paper_status,
    get_stuck_papers,
    delete_paper,
)
from infrastructure.db.crud.session_crud import (
    create_session,
    get_session,
    list_sessions,
    rename_session,
    delete_session,
)
from infrastructure.db.crud.message_crud import (
    create_message,
    get_messages_by_session,
    count_messages_by_session,
    get_recent_messages,
    delete_messages_by_session,
)
from infrastructure.db.crud.chunk_crud import (
    create_chunks_bulk,
    get_chunks_by_paper,
    get_chunk_by_paragraph_id,
    get_chunks_by_ids,
    delete_chunks_by_paper,
)

__all__ = [
    # Paper
    "create_paper",
    "get_paper",
    "get_papers_by_session",
    "update_paper_status",
    "get_stuck_papers",
    "delete_paper",
    # Session
    "create_session",
    "get_session",
    "list_sessions",
    "rename_session",
    "delete_session",
    # Message
    "create_message",
    "get_messages_by_session",
    "count_messages_by_session",
    "get_recent_messages",
    "delete_messages_by_session",
    # Chunk
    "create_chunks_bulk",
    "get_chunks_by_paper",
    "get_chunk_by_paragraph_id",
    "get_chunks_by_ids",
    "delete_chunks_by_paper",
]
