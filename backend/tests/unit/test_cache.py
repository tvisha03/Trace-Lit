"""TraceLit — TTLCache Unit Tests."""

import time
import pytest
from shared.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_missing_key(self):
        cache = TTLCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        cache = TTLCache(maxsize=10, ttl=0.1)  # 100ms TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_maxsize_eviction(self):
        cache = TTLCache(maxsize=2, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict oldest
        assert cache.size <= 2
        assert cache.get("c") == 3

    def test_invalidate(self):
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0

    def test_overwrite(self):
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"
