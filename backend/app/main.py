import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import asyncio

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.lifespan import lifespan
from api.v1.router import api_v1_router
from api.v1.routes.websocket import router as ws_router

# IMP-9: Default request timeout (seconds).  Streaming and WebSocket requests
# are excluded because they are long-lived by design.
_REQUEST_TIMEOUT_SECONDS: float = 120.0


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID header to every request/response.

    Enables end-to-end tracing: the frontend receives the header and can
    include it in bug reports; the backend logs can be correlated by ID.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Store on request.state so downstream handlers/loggers can access it.
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimeoutMiddleware(BaseHTTPMiddleware):
    """IMP-9: Abort requests that exceed a hard time limit.

    Streaming (SSE) and WebSocket upgrades are excluded because they are
    inherently long-lived.  All other endpoints get a configurable timeout
    to prevent slow LLM calls or runaway DB queries from tying up workers.
    """

    def __init__(self, app, timeout: float = _REQUEST_TIMEOUT_SECONDS):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        # Skip timeout for WebSocket upgrades and streaming endpoints.
        if (
            request.url.path.startswith("/ws")
            or "text/event-stream" in request.headers.get("accept", "")
            or request.query_params.get("stream") == "true"
        ):
            return await call_next(request)

        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"Request timed out after {self.timeout:.0f}s. "
                              "Please try again or simplify your query."
                },
            )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Intelligent Academic Literature Assistant with Sentence-Level Verified Attribution",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request-ID middleware — adds X-Request-ID for end-to-end tracing.
    app.add_middleware(RequestIDMiddleware)

    # IMP-9: Timeout middleware — aborts requests exceeding the time limit.
    # Added after RequestID so the timeout fires inside the request-id scope.
    app.add_middleware(TimeoutMiddleware)

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    # WebSocket routes are mounted at the app root (no versioning) so the frontend
    # can connect via ws://host/ws/{session_id} without a versioned prefix.
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

    return app

app = create_app()
