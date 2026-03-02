"""TraceLit — Rate Limit Monitor.

Proactive sliding-window token and request tracking per LLM provider.
Warns when approaching provider rate limits so the fallback chain can
pre-emptively switch before hitting a 429.

Provider budgets (free tier):
    Gemini: 250,000 TPM / 15 RPM
    Groq:   30,000 TPM / 30 RPM
    Ollama: unlimited (local)
"""

import time
import threading
from collections import deque
from typing import Dict, Optional

from loguru import logger


# ============================================================
# Provider rate limits
# ============================================================

PROVIDER_LIMITS: Dict[str, Dict[str, int]] = {
    "gemini": {"tpm": 250_000, "rpm": 15},
    "groq": {"tpm": 30_000, "rpm": 30},
    "ollama": {"tpm": 0, "rpm": 0},  # unlimited
}

# Warn when usage exceeds this fraction of the limit
WARNING_THRESHOLD = 0.80


class _SlidingWindowCounter:
    """Counts events within a rolling 60-second window."""

    def __init__(self):
        self._events: deque = deque()
        self._lock = threading.Lock()

    def record(self, value: int = 1) -> None:
        """Record an event with the given value (e.g., token count)."""
        now = time.time()
        with self._lock:
            self._events.append((now, value))
            self._prune(now)

    def total(self) -> int:
        """Sum of values in the last 60 seconds."""
        now = time.time()
        with self._lock:
            self._prune(now)
            return sum(v for _, v in self._events)

    def count(self) -> int:
        """Number of events in the last 60 seconds."""
        now = time.time()
        with self._lock:
            self._prune(now)
            return len(self._events)

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()


class RateLimitMonitor:
    """Per-provider sliding-window rate limit monitor.

    Tracks tokens and requests in a 60-second window and warns
    when approaching the configured limits.
    """

    def __init__(self):
        self._token_counters: Dict[str, _SlidingWindowCounter] = {}
        self._request_counters: Dict[str, _SlidingWindowCounter] = {}

    def _ensure_provider(self, provider: str) -> None:
        if provider not in self._token_counters:
            self._token_counters[provider] = _SlidingWindowCounter()
            self._request_counters[provider] = _SlidingWindowCounter()

    def record_request(self, provider: str, tokens: int = 0) -> None:
        """Record a completed request with its token count."""
        self._ensure_provider(provider)
        self._request_counters[provider].record(1)
        if tokens > 0:
            self._token_counters[provider].record(tokens)

    def is_approaching_limit(self, provider: str) -> bool:
        """Check if provider is approaching its rate limit.

        Returns True if either TPM or RPM usage exceeds the warning threshold.
        """
        limits = PROVIDER_LIMITS.get(provider.lower(), {})
        if not limits or (limits["tpm"] == 0 and limits["rpm"] == 0):
            return False  # unlimited

        self._ensure_provider(provider)

        tpm_limit = limits["tpm"]
        rpm_limit = limits["rpm"]

        current_tpm = self._token_counters[provider].total()
        current_rpm = self._request_counters[provider].count()

        approaching = False
        if tpm_limit > 0 and current_tpm >= tpm_limit * WARNING_THRESHOLD:
            logger.warning(
                "Provider {} approaching TPM limit: {}/{} ({}%)",
                provider, current_tpm, tpm_limit,
                round(100 * current_tpm / tpm_limit, 1),
            )
            approaching = True

        if rpm_limit > 0 and current_rpm >= rpm_limit * WARNING_THRESHOLD:
            logger.warning(
                "Provider {} approaching RPM limit: {}/{} ({}%)",
                provider, current_rpm, rpm_limit,
                round(100 * current_rpm / rpm_limit, 1),
            )
            approaching = True

        return approaching

    def get_usage(self, provider: str) -> Dict:
        """Get current usage statistics for a provider."""
        self._ensure_provider(provider)
        limits = PROVIDER_LIMITS.get(provider.lower(), {"tpm": 0, "rpm": 0})

        current_tpm = self._token_counters[provider].total()
        current_rpm = self._request_counters[provider].count()

        return {
            "provider": provider,
            "tokens_per_minute": current_tpm,
            "requests_per_minute": current_rpm,
            "tpm_limit": limits["tpm"],
            "rpm_limit": limits["rpm"],
            "tpm_pct": round(100 * current_tpm / limits["tpm"], 1) if limits["tpm"] > 0 else 0.0,
            "rpm_pct": round(100 * current_rpm / limits["rpm"], 1) if limits["rpm"] > 0 else 0.0,
        }

    def get_all_usage(self) -> Dict[str, Dict]:
        """Get usage for all tracked providers."""
        return {p: self.get_usage(p) for p in self._token_counters}


# ============================================================
# Module-level singleton
# ============================================================
_monitor_instance: Optional[RateLimitMonitor] = None


def get_rate_limit_monitor() -> RateLimitMonitor:
    """Get or create the global rate limit monitor."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = RateLimitMonitor()
    return _monitor_instance
