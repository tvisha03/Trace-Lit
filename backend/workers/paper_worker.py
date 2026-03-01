"""TraceLit — Paper Processing Worker (Phase 2 async task stub).

In Phase 2, synchronous paper processing will be offloaded to a
Celery/ARQ background worker. This module is the entry point for
that future implementation.
"""

import asyncio
from typing import Any, Dict

from loguru import logger


async def process_paper_task(paper_id: str, file_path: str) -> Dict[str, Any]:
    """Process a single paper asynchronously (Phase 2 entry point).

    In Phase 1, paper processing is synchronous inside the request cycle.
    This function signature is reserved for the Phase 2 task queue.

    Args:
        paper_id: Paper UUID.
        file_path: Absolute path to the uploaded PDF file.

    Returns:
        Dict with status, paper_id, and any error details.
    """
    logger.info("Worker received task: process_paper paper_id={}", paper_id)
    # TODO Phase 2: implement async worker with progress reporting via WebSocket
    raise NotImplementedError(
        "Async paper processing worker is not yet implemented (Phase 2)."
    )
