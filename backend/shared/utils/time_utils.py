"""TraceLit — Time utilities."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(tz=timezone.utc)


def iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utcnow().isoformat()
