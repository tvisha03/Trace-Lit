import json
from typing import Any, AsyncGenerator


def sse_event(event: str, data: Any) -> str:
    """
    Format a single SSE frame.

    Returns a string like:
        event: chat_token
        data: {"token": "Hello"}

    Follows the W3C Server-Sent Events spec.
    """
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def sse_stream(
    generator: AsyncGenerator[tuple[str, Any], None],
) -> AsyncGenerator[str, None]:
    """
    Wrap an async generator of (event_name, data) tuples into SSE frames.

    Usage in a FastAPI StreamingResponse:
        return StreamingResponse(
            sse_stream(my_generator()),
            media_type="text/event-stream",
        )
    """
    async for event_name, data in generator:
        yield sse_event(event_name, data)

    # Signal end-of-stream
    yield sse_event("done", {"status": "complete"})
