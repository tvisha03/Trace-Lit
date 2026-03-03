
import json
import time
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from threading import Lock

from shared.enums import LLMProvider
from shared.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Persistence (HI-004 fix)
# ---------------------------------------------------------------------------
# Rate-usage state is saved to a JSON file so the 60-second sliding window
# survives server restarts.  Only entries that are still within their window
# are written/read, so stale data is never resurrected.
# The file path can be changed via the RATE_MONITOR_STATE_FILE env variable.
# ---------------------------------------------------------------------------
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
        "rpm": 15,
    },
    LLMProvider.GROQ.value: {
        "tpm": 30_000,
        "rpm": 30,
    },
    LLMProvider.OLLAMA.value: {
        "tpm": 999_999,
        "rpm": 999,
    },
}

_SAFETY_MARGIN: float = 0.90

@dataclass
class _UsageEntry:
    # Wall-clock UNIX timestamp (time.time()) so entries can be persisted and
    # compared correctly after a server restart (HI-004 fix).
    timestamp: float
    tokens: int

@dataclass
class _ProviderUsage:
    entries: deque[_UsageEntry] = field(default_factory=deque)
    lock: Lock = field(default_factory=Lock)

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self.entries and self.entries[0].timestamp < cutoff:
            self.entries.popleft()

    def record(self, tokens: int) -> None:
        # Use wall-clock time so timestamps survive serialisation (HI-004).
        now = time.time()
        with self.lock:
            self._prune(now)
            self.entries.append(_UsageEntry(timestamp=now, tokens=tokens))

    def current_tpm(self) -> int:
        now = time.time()
        with self.lock:
            self._prune(now)
            return sum(e.tokens for e in self.entries)

    def current_rpm(self) -> int:
        now = time.time()
        with self.lock:
            self._prune(now)
            return len(self.entries)

    def to_dict(self) -> list[dict]:
        """Serialise non-expired entries for persistence."""
        now = time.time()
        with self.lock:
            self._prune(now)
            return [{"ts": e.timestamp, "tok": e.tokens} for e in self.entries]

    def load_dict(self, data: list[dict]) -> None:
        """Restore entries from a previously persisted snapshot."""
        now = time.time()
        cutoff = now - 60.0
        with self.lock:
            self.entries.clear()
            for e in data:
                ts = e.get("ts", 0.0)
                if ts > cutoff:  # discard already-expired entries
                    self.entries.append(_UsageEntry(timestamp=ts, tokens=e.get("tok", 0)))

class RateLimitMonitor:

    # Batch persistence: save to disk at most every _SAVE_INTERVAL seconds or
    # every _SAVE_EVERY_N_CALLS track_usage invocations, whichever comes first.
    _SAVE_INTERVAL: float = 30.0
    _SAVE_EVERY_N_CALLS: int = 10

    def __init__(self) -> None:
        self._usage: dict[str, _ProviderUsage] = {
            provider: _ProviderUsage()
            for provider in _PROVIDER_LIMITS
        }
        self._calls_since_save: int = 0
        self._last_save_time: float = time.time()
        # Attempt to restore token-usage state from the previous run so the
        # 60-second sliding window is honoured across server restarts (HI-004).
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers (HI-004 fix)
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Persist current sliding-window entries to disk (best-effort)."""
        try:
            _PERSISTENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {name: usage.to_dict() for name, usage in self._usage.items()}
            _PERSISTENCE_PATH.write_text(json.dumps(snapshot), encoding="utf-8")
        except Exception as exc:
            # Non-fatal — rate limiting degrades to stateless on I/O errors.
            logger.debug(f"Rate-monitor state save failed (non-fatal): {exc}")

    def _load_state(self) -> None:
        """Restore persisted entries, ignoring any that are already expired."""
        if not _PERSISTENCE_PATH.exists():
            return
        try:
            snapshot: dict = json.loads(_PERSISTENCE_PATH.read_text(encoding="utf-8"))
            for provider_name, entries in snapshot.items():
                usage = self._usage.get(provider_name)
                if usage and isinstance(entries, list):
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

        if not has_token_room or not has_request_room:
            logger.info(
                f"Rate limit pre-check FAILED for {provider.value}: "
                f"TPM {current_tokens}+{estimated_tokens}/{max_tpm}, "
                f"RPM {current_requests}+1/{max_rpm}"
            )
            return False

        return True

    def track_usage(self, provider: LLMProvider, tokens_used: int) -> None:
        usage = self._usage.get(provider.value)
        if usage:
            usage.record(tokens_used)
            logger.debug(
                f"Tracked {tokens_used} tokens for {provider.value} "
                f"(window TPM: {usage.current_tpm()}, RPM: {usage.current_rpm()})"
            )
            # BUG-F fix: batch persistence — save to disk only when the call
            # count or elapsed-time threshold is exceeded, not on every call.
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
            summary[provider_name] = {
                "current_tpm": usage.current_tpm(),
                "max_tpm": limits.get("tpm", 0),
                "current_rpm": usage.current_rpm(),
                "max_rpm": limits.get("rpm", 0),
            }
        return summary
