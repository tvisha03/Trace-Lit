import time
from contextlib import contextmanager
from typing import Generator

from shared.logger import get_logger, log_performance

logger = get_logger(__name__)


@contextmanager
def timer(operation: str, target_ms: float = 0, extra: dict | None = None) -> Generator[None, None, None]:
    """
    Context manager that measures wall-clock time and logs performance.

    Usage:
        with timer("vector_retrieval", target_ms=100, extra={"papers": 3}):
            results = faiss_store.search(query_vec)
    """
    start = time.perf_counter()
    yield
    elapsed_ms = (time.perf_counter() - start) * 1000

    if target_ms > 0:
        log_performance(logger, operation, elapsed_ms, target_ms, extra)
    else:
        logger.debug(f"[TIMER] {operation}: {elapsed_ms:.1f}ms")


def timestamp_ms() -> int:
    """Current wall-clock timestamp in milliseconds (for ETA calculations)."""
    return int(time.time() * 1000)
