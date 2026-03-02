import json
from typing import Any, AsyncGenerator

def sse_event(event: str, data: Any) -> str:
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"

async def sse_stream(
    generator: AsyncGenerator[tuple[str, Any], None],
) -> AsyncGenerator[str, None]:
    async for event_name, data in generator:
        yield sse_event(event_name, data)

    yield sse_event("done", {"status": "complete"})
