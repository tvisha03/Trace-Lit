
from app.config import get_settings
from shared.logger import get_logger

logger = get_logger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    logger.warning(
        "psutil not installed — memory pressure monitoring disabled. "
        "Install with: pip install psutil"
    )

def is_memory_pressure_high(threshold: float | None = None) -> bool:
    if threshold is None:
        threshold = get_settings().MEMORY_PRESSURE_THRESHOLD
    if not _PSUTIL_AVAILABLE:
        return False

    mem = psutil.virtual_memory()
    usage_ratio = mem.percent / 100.0

    if usage_ratio > threshold:
        logger.warning(
            f"Memory pressure HIGH: {mem.percent:.1f}% used "
            f"({_human_bytes(mem.used)}/{_human_bytes(mem.total)}), "
            f"threshold={threshold * 100:.0f}%"
        )
        return True
    return False

def get_memory_stats() -> dict:
    if not _PSUTIL_AVAILABLE:
        return {
            "total": 0,
            "available": 0,
            "used": 0,
            "percent": 0.0,
            "pressure_high": False,
            "psutil_available": False,
        }

    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": round(mem.percent, 1),
        "pressure_high": is_memory_pressure_high(),
        "psutil_available": True,
    }

def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n = int(n / 1024)
    return f"{n:.1f} PB"

