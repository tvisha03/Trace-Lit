"""TraceLit — Memory Monitor Unit Tests."""

import pytest
from shared.memory_monitor import MemoryMonitor


class TestMemoryMonitor:
    def test_check_memory_returns_dict(self):
        monitor = MemoryMonitor()
        status = monitor.check_memory()
        assert "level" in status
        assert "system_percent" in status
        assert "process_rss_gb" in status
        assert "available_gb" in status
        assert "total_gb" in status
        assert status["level"] in ("ok", "warning", "high", "critical")

    def test_is_safe_for_heavy_op(self):
        monitor = MemoryMonitor()
        # On any reasonable dev machine this should be True
        result = monitor.is_safe_for_heavy_op()
        assert isinstance(result, bool)

    def test_start_stop(self):
        monitor = MemoryMonitor(poll_interval_s=0.1)
        monitor.start()
        assert monitor._running is True
        monitor.stop()
        assert monitor._running is False
