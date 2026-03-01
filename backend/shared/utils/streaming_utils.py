"""TraceLit — SSE (Server-Sent Events) helpers shared across features."""

import json
from typing import Any, AsyncIterator


def sse_event(event_type: str, data: Any) -> str:
    """Format a single SSE message.

    Args:
        event_type: Event type string (e.g. "chunk", "done", "error").
        data: JSON-serialisable payload.

    Returns:
        Formatted SSE string ending with double newline.
    """
    if isinstance(data, dict):
        payload = {"type": event_type, **data}
    else:
        payload = {"type": event_type, "payload": data}
    return "data: " + json.dumps(payload) + "\n\n"


def sse_chunk(text: str) -> str:
    """Shorthand for a streaming text chunk event."""
    return sse_event("chunk", {"text": text})


def sse_error(message: str) -> str:
    """Shorthand for a streaming error event."""
    return sse_event("error", {"message": message})


def sse_done(metadata: dict) -> str:
    """Shorthand for the final done event carrying metadata."""
    return sse_event("done", {"metadata": metadata})


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}
