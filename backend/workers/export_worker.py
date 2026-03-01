import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from shared.logger import get_logger

logger = get_logger(__name__)

# Dedicated thread pool for export tasks (WeasyPrint is not async-safe)
_export_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="export")


async def run_export_in_thread(
    export_fn: Callable[..., Path],
    *args,
    **kwargs,
) -> Path:
    loop = asyncio.get_running_loop()

    def _wrapped():
        return export_fn(*args, **kwargs)

    result = await loop.run_in_executor(_export_executor, _wrapped)
    logger.info(f"Export completed: {result}")
    return result

def shutdown_export_pool():
    _export_executor.shutdown(wait=True)
    logger.info("Export thread pool shut down")
