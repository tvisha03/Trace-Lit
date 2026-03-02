"""TraceLit — Memory Monitor.

Monitors system memory usage and provides defensive actions
when thresholds are exceeded. Designed for M3 MacBook Pro
with 8 GB unified memory.

Thresholds:
    70% — INFO log, start monitoring more frequently
    80% — WARNING log, trigger GC
    90% — CRITICAL, unload idle models (cross-encoder), reduce batch sizes
"""

import gc
import threading
import time
from typing import Callable, Dict, List, Optional

import psutil
from loguru import logger


# ============================================================
# Thresholds (percentage of total RAM)
# ============================================================
MEMORY_WARNING_PERCENT = 70.0
MEMORY_HIGH_PERCENT = 80.0
MEMORY_CRITICAL_PERCENT = 90.0

# Hard limit for the process itself (GB)
PROCESS_MEMORY_WARN_GB = 5.5
PROCESS_MEMORY_HARD_LIMIT_GB = 6.0


class MemoryMonitor:
    """Background memory monitor with threshold-based actions.

    Uses a lightweight daemon thread to poll RSS at configurable intervals.
    """

    def __init__(
        self,
        poll_interval_s: float = 30.0,
        on_warning: Optional[Callable] = None,
        on_critical: Optional[Callable] = None,
    ):
        self._poll_interval = poll_interval_s
        self._on_warning = on_warning
        self._on_critical = on_critical
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_level = "ok"
        self._process = psutil.Process()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="memory-monitor")
        self._thread.start()
        logger.info("Memory monitor started (poll={}s)", self._poll_interval)

    def stop(self) -> None:
        """Stop the monitor thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def check_memory(self) -> Dict:
        """One-shot memory check. Returns current status dict."""
        vm = psutil.virtual_memory()
        rss_gb = self._process.memory_info().rss / (1024 ** 3)
        percent = vm.percent

        level = "ok"
        if percent >= MEMORY_CRITICAL_PERCENT or rss_gb >= PROCESS_MEMORY_HARD_LIMIT_GB:
            level = "critical"
        elif percent >= MEMORY_HIGH_PERCENT or rss_gb >= PROCESS_MEMORY_WARN_GB:
            level = "high"
        elif percent >= MEMORY_WARNING_PERCENT:
            level = "warning"

        return {
            "level": level,
            "system_percent": round(percent, 1),
            "process_rss_gb": round(rss_gb, 2),
            "available_gb": round(vm.available / (1024 ** 3), 2),
            "total_gb": round(vm.total / (1024 ** 3), 2),
        }

    def is_safe_for_heavy_op(self) -> bool:
        """Return True if memory is safe for large operations (embedding, cross-encoder)."""
        status = self.check_memory()
        return status["level"] in ("ok", "warning")

    # ----------------------------------------------------------
    # Internals
    # ----------------------------------------------------------

    def _run(self) -> None:
        while self._running:
            try:
                status = self.check_memory()
                level = status["level"]

                # Only log on level transitions
                if level != self._last_level:
                    if level == "critical":
                        logger.critical(
                            "Memory CRITICAL: system={}%, process={} GB",
                            status["system_percent"], status["process_rss_gb"],
                        )
                        self._handle_critical()
                    elif level == "high":
                        logger.warning(
                            "Memory HIGH: system={}%, process={} GB — triggering GC",
                            status["system_percent"], status["process_rss_gb"],
                        )
                        gc.collect()
                    elif level == "warning":
                        logger.info(
                            "Memory WARNING: system={}%, process={} GB",
                            status["system_percent"], status["process_rss_gb"],
                        )
                    elif self._last_level != "ok":
                        logger.info(
                            "Memory back to OK: system={}%, process={} GB",
                            status["system_percent"], status["process_rss_gb"],
                        )

                    self._last_level = level

            except Exception as e:
                logger.error("Memory monitor error: {}", e)

            time.sleep(self._poll_interval)

    def _handle_critical(self) -> None:
        """Emergency actions on critical memory."""
        gc.collect()

        # Unload cross-encoder if possible
        try:
            from domain.verification.havf import get_havf
            havf = get_havf()
            if hasattr(havf, "_cross_encoder") and havf._cross_encoder is not None:
                havf._cross_encoder = None
                logger.warning("Unloaded cross-encoder to free memory")
                gc.collect()
        except Exception:
            pass

        if self._on_critical:
            try:
                self._on_critical()
            except Exception:
                pass


# ============================================================
# Module-level singleton
# ============================================================
_monitor_instance: Optional[MemoryMonitor] = None


def get_memory_monitor() -> MemoryMonitor:
    """Get or create the global memory monitor."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = MemoryMonitor()
    return _monitor_instance
