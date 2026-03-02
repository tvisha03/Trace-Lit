"""TraceLit — Rate Limit Monitor Unit Tests."""

import pytest
from shared.rate_limit_monitor import RateLimitMonitor, PROVIDER_LIMITS


class TestRateLimitMonitor:
    def test_record_and_check(self):
        monitor = RateLimitMonitor()
        monitor.record_request("gemini", tokens=1000)
        assert not monitor.is_approaching_limit("gemini")

    def test_approaching_limit(self):
        monitor = RateLimitMonitor()
        # Simulate many requests to approach RPM limit (15 for Gemini)
        for _ in range(13):  # 80% of 15 = 12
            monitor.record_request("gemini", tokens=100)
        assert monitor.is_approaching_limit("gemini")

    def test_get_usage(self):
        monitor = RateLimitMonitor()
        monitor.record_request("groq", tokens=5000)
        usage = monitor.get_usage("groq")
        assert usage["provider"] == "groq"
        assert usage["tokens_per_minute"] == 5000
        assert usage["requests_per_minute"] == 1

    def test_unlimited_provider(self):
        monitor = RateLimitMonitor()
        monitor.record_request("ollama", tokens=100000)
        assert not monitor.is_approaching_limit("ollama")

    def test_get_all_usage(self):
        monitor = RateLimitMonitor()
        monitor.record_request("gemini", tokens=100)
        monitor.record_request("groq", tokens=200)
        all_usage = monitor.get_all_usage()
        assert "gemini" in all_usage
        assert "groq" in all_usage
