"""TraceLit — Centralised Logging Configuration.

Call configure_logging() once at application startup.
All modules use `from loguru import logger` directly after this.
"""

import sys
from pathlib import Path

from loguru import logger


def configure_logging(log_level: str = "INFO", log_file: str = "./data/logs/tracelit.log") -> None:
    """Set up loguru with console + rotating file handlers.

    Args:
        log_level: Minimum log level for console output.
        log_file: Path to the rotating log file.
    """
    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="5 days",
        compression="zip",
        format="{time} | {level} | {name}:{function}:{line} | {message}",
    )
