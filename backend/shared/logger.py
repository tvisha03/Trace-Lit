import logging
import sys
from typing import Any


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Initialise root logger with a clean console handler."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger scoped to *name*."""
    return logging.getLogger(name)


def log_performance(
    logger: logging.Logger,
    operation: str,
    duration_ms: float,
    target_ms: float,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Emit a performance metric line.
    Marks ✅ if within target, ⚠️ if over.
    """
    status = "✅" if duration_ms <= target_ms else "⚠️"
    parts = f"[PERF] {operation}: {duration_ms:.1f}ms {status} (target: {target_ms:.0f}ms)"
    if extra:
        detail = " | ".join(f"{k}={v}" for k, v in extra.items())
        parts += f" | {{{detail}}}"
    logger.info(parts)
