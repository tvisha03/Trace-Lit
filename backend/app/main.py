import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.lifespan import lifespan
from api.v1.router import api_v1_router
from api.v1.routes.websocket import router as ws_router


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

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    # WebSocket routes are mounted at the app root (no versioning) so the frontend
    # can connect via ws://host/ws/{session_id} without a versioned prefix.
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

    return app

app = create_app()
