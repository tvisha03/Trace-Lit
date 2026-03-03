"""Shared in-memory sliding-window rate limiter.

Extracts the duplicate rate-limiter pattern from papers.py and
verification.py into a single reusable utility (MINOR-001).

All endpoint-specific rate limiters should instantiate ``SlidingWindowRateLimiter``
with appropriate limits rather than re-implementing the algorithm.

PRODUCTION NOTE (HI-001): This is an in-memory implementation and is
NOT suitable for multi-instance / multi-worker deployments.  In those
environments counters are not shared between processes, so the window can
be exceeded by a factor equal to the worker count.  Migrate to a
Redis-backed rate limiter before scaling horizontally.
"""

from collections import defaultdict
from time import monotonic

from fastapi import HTTPException, Request

from shared.logger import get_logger

logger = get_logger(__name__)


def _resolve_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For behind proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For may contain a chain: "client, proxy1, proxy2"
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class SlidingWindowRateLimiter:
    """Per-client-IP sliding-window rate limiter.

    Parameters
    ----------
    max_calls:
        Maximum number of requests allowed per window.
    window_seconds:
        Duration (in seconds) of the sliding window.
    resource_name:
        Human-readable label for error messages (e.g. "upload", "chat").
    """

    def __init__(
        self,
        max_calls: int,
        window_seconds: float,
        resource_name: str = "requests",
    ) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._resource_name = resource_name
        self._calls: dict[str, list[float]] = defaultdict(list)

    def enforce(self, request: Request) -> None:
        """Raise HTTP 429 if the caller has exceeded the rate limit."""
        client_ip = _resolve_client_ip(request)
        now = monotonic()
        cutoff = now - self._window_seconds

        # Evict timestamps outside the sliding window.
        calls = self._calls[client_ip]
        self._calls[client_ip] = [t for t in calls if t > cutoff]

        if len(self._calls[client_ip]) >= self._max_calls:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: max {self._max_calls} {self._resource_name} "
                    f"per {int(self._window_seconds)} seconds."
                ),
            )

        self._calls[client_ip].append(now)

        # Periodic cleanup: every 100 enforce() calls, evict stale IPs that
        # have no timestamps inside the current window.  This prevents the
        # _calls dict from growing unboundedly when many unique IPs hit the
        # server (EDGE-7 fix).
        total_entries = sum(len(v) for v in self._calls.values())
        if total_entries > 100:
            stale_ips = [
                ip for ip, ts in self._calls.items()
                if not ts or ts[-1] <= cutoff
            ]
            for ip in stale_ips:
                del self._calls[ip]

    def reset(self) -> None:
        """Clear all tracked calls — useful for testing."""
        self._calls.clear()
