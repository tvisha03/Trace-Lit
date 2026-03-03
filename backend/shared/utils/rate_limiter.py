
from collections import defaultdict
from time import monotonic

from fastapi import HTTPException, Request

from shared.logger import get_logger

logger = get_logger(__name__)


def _resolve_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class SlidingWindowRateLimiter:

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
        client_ip = _resolve_client_ip(request)
        now = monotonic()
        cutoff = now - self._window_seconds

        self._clean_expired_calls(client_ip, cutoff)
        self._check_rate_limit(client_ip)
        self._record_call(client_ip, now)
        self._cleanup_stale_clients(cutoff)

    def _clean_expired_calls(self, client_ip: str, cutoff: float) -> None:
        calls = self._calls[client_ip]
        self._calls[client_ip] = [t for t in calls if t > cutoff]

    def _check_rate_limit(self, client_ip: str) -> None:
        if len(self._calls[client_ip]) >= self._max_calls:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: max {self._max_calls} {self._resource_name} "
                    f"per {int(self._window_seconds)} seconds."
                ),
            )

    def _record_call(self, client_ip: str, now: float) -> None:
        self._calls[client_ip].append(now)

    def _cleanup_stale_clients(self, cutoff: float) -> None:
        total_entries = sum(len(v) for v in self._calls.values())
        if total_entries > 100:
            stale_ips = [
                ip for ip, ts in self._calls.items()
                if not ts or ts[-1] <= cutoff
            ]
            for ip in stale_ips:
                del self._calls[ip]

    def reset(self) -> None:
        self._calls.clear()

