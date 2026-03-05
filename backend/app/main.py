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

class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

class TimeoutMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, timeout: float):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
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

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout=settings.REQUEST_TIMEOUT)

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

    return app

app = create_app()

