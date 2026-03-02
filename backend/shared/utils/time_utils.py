import time
from contextlib import contextmanager
from typing import Generator

from shared.logger import get_logger, log_performance

logger = get_logger(__name__)

@contextmanager
def timer(operation: str, target_ms: float = 0, extra: dict | None = None) -> Generator[None, None, None]:
    start = time.perf_counter()
    yield
    elapsed_ms = (time.perf_counter() - start) * 1000

    if target_ms > 0:
        log_performance(logger, operation, elapsed_ms, target_ms, extra)
    else:
        logger.debug(f"[TIMER] {operation}: {elapsed_ms:.1f}ms")

def timestamp_ms() -> int:
    return int(time.time() * 1000)
