
import json
import time
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from threading import Lock

from shared.enums import LLMProvider
from shared.logger import get_logger

logger = get_logger(__name__)

import os as _os
_PERSISTENCE_PATH = Path(
    _os.environ.get(
        "RATE_MONITOR_STATE_FILE",
        str(Path(__file__).parent.parent.parent / "data" / ".rate_monitor_state.json"),
    )
)

_PROVIDER_LIMITS: dict[str, dict[str, int]] = {
    LLMProvider.GEMINI.value: {
        "tpm": 250_000,
        "rpm": 20,
        "rpd": 200,
    },
    LLMProvider.GROQ.value: {
        "tpm": 12_000,
        "rpm": 30,
        "rpd": 1_000,
    },
    LLMProvider.OLLAMA.value: {
        "tpm": 999_999,
        "rpm": 999,
    },
    LLMProvider.OLLAMA_CLOUD.value: {
        "tpm": 200_000,
        "rpm": 30,
    },
}

_SAFETY_MARGIN: float = 0.85
_DAY_SECONDS: float = 86_400.0

@dataclass
class _UsageEntry:
    timestamp: float
    tokens: int

@dataclass
class _ProviderUsage:
    entries: deque[_UsageEntry] = field(default_factory=deque)
    daily_entries: deque[_UsageEntry] = field(default_factory=deque)
    lock: Lock = field(default_factory=Lock)

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self.entries and self.entries[0].timestamp < cutoff:
            self.entries.popleft()
        day_cutoff = now - _DAY_SECONDS
        while self.daily_entries and self.daily_entries[0].timestamp < day_cutoff:
            self.daily_entries.popleft()

    def record(self, tokens: int) -> None:
        now = time.time()
        with self.lock:
            self._prune(now)
            entry = _UsageEntry(timestamp=now, tokens=tokens)
            self.entries.append(entry)
            self.daily_entries.append(entry)

    def current_tpm(self) -> int:
        now = time.time()
        with self.lock:
            self._prune(now)
            return sum(e.tokens for e in self.entries)

    def current_rpd(self) -> int:
        now = time.time()
        with self.lock:
            self._prune(now)
            return len(self.daily_entries)

    def current_rpm(self) -> int:
        now = time.time()
        with self.lock:
            self._prune(now)
            return len(self.entries)

    def to_dict(self) -> dict:
        now = time.time()
        with self.lock:
            self._prune(now)
            return {
                "entries": [{"ts": e.timestamp, "tok": e.tokens} for e in self.entries],
                "daily": [{"ts": e.timestamp, "tok": e.tokens} for e in self.daily_entries],
            }

    def load_dict(self, data: dict | list) -> None:
        now = time.time()
        cutoff = now - 60.0
        day_cutoff = now - _DAY_SECONDS

        # Backward-compatible: accept old list format or new dict format
        if isinstance(data, list):
            entries_data = data
            daily_data: list[dict] = []
        else:
            entries_data = data.get("entries", [])
            daily_data = data.get("daily", [])

        with self.lock:
            self.entries.clear()
            for e in entries_data:
                ts = e.get("ts", 0.0)
                if ts > cutoff:
                    self.entries.append(_UsageEntry(timestamp=ts, tokens=e.get("tok", 0)))
            self.daily_entries.clear()
            for e in daily_data:
                ts = e.get("ts", 0.0)
                if ts > day_cutoff:
                    self.daily_entries.append(_UsageEntry(timestamp=ts, tokens=e.get("tok", 0)))

class RateLimitMonitor:

    _SAVE_INTERVAL: float = 30.0
    _SAVE_EVERY_N_CALLS: int = 10

    def __init__(self) -> None:
        self._usage: dict[str, _ProviderUsage] = {
            provider: _ProviderUsage()
            for provider in _PROVIDER_LIMITS
        }
        self._calls_since_save: int = 0
        self._last_save_time: float = time.time()
        self._load_state()

    def _save_state(self) -> None:
        try:
            _PERSISTENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {name: usage.to_dict() for name, usage in self._usage.items()}
            _PERSISTENCE_PATH.write_text(json.dumps(snapshot), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"Rate-monitor state save failed (non-fatal): {exc}")

    def _load_state(self) -> None:
        if not _PERSISTENCE_PATH.exists():
            return
        try:
            snapshot: dict = json.loads(_PERSISTENCE_PATH.read_text(encoding="utf-8"))
            for provider_name, entries in snapshot.items():
                usage = self._usage.get(provider_name)
                if usage and isinstance(entries, (list, dict)):
                    usage.load_dict(entries)
            logger.info("Rate-monitor usage state restored from previous run")
        except Exception as exc:
            logger.warning(f"Could not restore rate-monitor state (will start fresh): {exc}")

    def can_make_request(
        self,
        provider: LLMProvider,
        estimated_tokens: int = 8_500,
    ) -> bool:
        limits = _PROVIDER_LIMITS.get(provider.value)
        if not limits:
            return True

        usage = self._usage.get(provider.value)
        if not usage:
            return True

        max_tpm = int(limits["tpm"] * _SAFETY_MARGIN)
        max_rpm = int(limits["rpm"] * _SAFETY_MARGIN)

        current_tokens = usage.current_tpm()
        current_requests = usage.current_rpm()

        has_token_room = (current_tokens + estimated_tokens) <= max_tpm
        has_request_room = (current_requests + 1) <= max_rpm

        # Check daily request limit if provider has one
        rpd_limit = limits.get("rpd")
        has_daily_room = True
        daily_requests = 0
        if rpd_limit:
            daily_requests = usage.current_rpd()
            has_daily_room = (daily_requests + 1) <= int(rpd_limit * _SAFETY_MARGIN)

        if not has_token_room or not has_request_room or not has_daily_room:
            logger.info(
                f"Rate limit pre-check FAILED for {provider.value}: "
                f"TPM {current_tokens}+{estimated_tokens}/{max_tpm}, "
                f"RPM {current_requests}+1/{max_rpm}"
                + (f", RPD {daily_requests}/{rpd_limit}" if rpd_limit else "")
            )
            return False

        return True

    def _minute_wait(self, usage: _ProviderUsage, current: int, limit: int, now: float) -> float:
        """Seconds until the per-minute window has room, or 0."""
        if current <= limit or not usage.entries:
            return 0.0
        return 60.0 - (now - usage.entries[0].timestamp) + 0.5

    def _daily_wait(self, usage: _ProviderUsage, rpd_limit: int | None, now: float) -> float:
        """Seconds until daily limit has room, or 0."""
        if not rpd_limit:
            return 0.0
        with usage.lock:
            daily_count = len(usage.daily_entries)
        max_rpd = int(rpd_limit * _SAFETY_MARGIN)
        if (daily_count + 1) <= max_rpd or not usage.daily_entries:
            return 0.0
        return _DAY_SECONDS - (now - usage.daily_entries[0].timestamp) + 1.0

    def seconds_until_available(
        self,
        provider: LLMProvider,
        estimated_tokens: int = 4_000,
    ) -> float:
        """Return seconds to wait before the provider has capacity, or 0 if ready."""
        limits = _PROVIDER_LIMITS.get(provider.value)
        if not limits:
            return 0.0

        usage = self._usage.get(provider.value)
        if not usage:
            return 0.0

        max_tpm = int(limits["tpm"] * _SAFETY_MARGIN)
        max_rpm = int(limits["rpm"] * _SAFETY_MARGIN)

        now = time.time()
        with usage.lock:
            usage._prune(now)
            current_tokens = sum(e.tokens for e in usage.entries)
            current_requests = len(usage.entries)

        tpm_wait = self._minute_wait(usage, current_tokens + estimated_tokens, max_tpm, now)
        rpm_wait = self._minute_wait(usage, current_requests + 1, max_rpm, now)
        rpd_wait = self._daily_wait(usage, limits.get("rpd"), now)

        wait = max(tpm_wait, rpm_wait, rpd_wait)

        return min(wait, 60.0) if wait <= 60.0 else wait

    def track_usage(self, provider: LLMProvider, tokens_used: int) -> None:
        usage = self._usage.get(provider.value)
        if usage:
            usage.record(tokens_used)
            logger.debug(
                f"Tracked {tokens_used} tokens for {provider.value} "
                f"(window TPM: {usage.current_tpm()}, RPM: {usage.current_rpm()})"
            )
            self._calls_since_save += 1
            now = time.time()
            if (
                self._calls_since_save >= self._SAVE_EVERY_N_CALLS
                or (now - self._last_save_time) >= self._SAVE_INTERVAL
            ):
                self._save_state()
                self._calls_since_save = 0
                self._last_save_time = now

    def get_available_provider(
        self,
        provider_order: list[LLMProvider],
        estimated_tokens: int = 8_500,
    ) -> LLMProvider | None:
        for provider in provider_order:
            if self.can_make_request(provider, estimated_tokens):
                return provider
        return None

    def get_usage_summary(self) -> dict[str, dict[str, int]]:
        summary = {}
        for provider_name, usage in self._usage.items():
            limits = _PROVIDER_LIMITS.get(provider_name, {})
            info: dict[str, int] = {
                "current_tpm": usage.current_tpm(),
                "max_tpm": limits.get("tpm", 0),
                "current_rpm": usage.current_rpm(),
                "max_rpm": limits.get("rpm", 0),
            }
            rpd_limit = limits.get("rpd")
            if rpd_limit:
                info["current_rpd"] = usage.current_rpd()
                info["max_rpd"] = rpd_limit
            summary[provider_name] = info
        return summary

