"""TraceLit — Caching Utilities.

Provides TTL-based caches for:
- Embedding vectors (avoid re-encoding identical text)
- Paper metadata (frequently accessed in chat pipeline)
- Provider rate limit state
"""

import time
import threading
from typing import Any, Dict, Optional


class TTLCache:
    """Simple thread-safe TTL cache using a dict.

    Entries expire after ``ttl`` seconds. Maximum size is enforced by
    evicting the oldest entry when capacity is reached.

    This avoids the ``cachetools`` dependency — light enough for our needs.
    """

    __slots__ = ("_store", "_maxsize", "_ttl", "_lock")

    def __init__(self, maxsize: int = 1000, ttl: float = 3600.0):
        self._store: Dict[str, tuple] = {}  # key → (value, expiry_ts)
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or None if missing/expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.time() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with TTL."""
        with self._lock:
            # Evict expired entries first
            now = time.time()
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]

            # Evict oldest if at capacity
            if len(self._store) >= self._maxsize:
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]

            self._store[key] = (value, now + self._ttl)

    def invalidate(self, key: str) -> None:
        """Remove a specific entry."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        """Number of live entries (may include recently expired)."""
        return len(self._store)


# ============================================================
# Global cache instances
# ============================================================

# Embedding cache: cache text → embedding vector (avoids re-encoding identical text)
# Keyed by hash of text content
_embedding_cache = TTLCache(maxsize=1000, ttl=3600)   # 1 hour TTL

# Paper metadata cache: paper_id → metadata dict (title, authors, year)
_paper_meta_cache = TTLCache(maxsize=100, ttl=300)     # 5 min TTL

# Provider stats cache: provider_name → recent success/failure counts
_provider_stats_cache = TTLCache(maxsize=10, ttl=600)  # 10 min TTL


def get_embedding_cache() -> TTLCache:
    return _embedding_cache


def get_paper_meta_cache() -> TTLCache:
    return _paper_meta_cache


def get_provider_stats_cache() -> TTLCache:
    return _provider_stats_cache
