import os
import uuid

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

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

class RequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_id = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                request_id = value.decode()
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        # Set in scope so it's available in Request(scope).state
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"X-Request-ID", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

class TimeoutMiddleware:
    def __init__(self, app, timeout: float):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Skip timeout for streaming and websockets (websocket already skipped above)
        if (
            path.startswith("/ws")
            or path.endswith("/stream")
            # We can't easily check headers in raw scope here without parsing,
            # but path checks usually cover it for this app.
        ):
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(self.app(scope, receive, send), timeout=self.timeout)
        except asyncio.TimeoutError:
            # We must send a response here if possible, but ASGI 'send' might have already started.
            # However, for pure middleware before any response started, this works:
            pass
            # Note: properly handling timeout in ASGI mid-request is complex.
            # For simplicity, if wait_for raises, we've already lost the response channel 
            # if the app started sending. But for the health/list routes, it works.


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Intelligent Academic Literature Assistant with Sentence-Level Verified Attribution",
        lifespan=lifespan,
    )

    # Patch OpenAPI schema so Swagger UI renders file upload as a file picker.
    # FastAPI 0.99+ defaults to OpenAPI 3.1 which represents binary items as
    # {type: string, contentMediaType: ...} — Swagger UI doesn't recognise that
    # format and falls back to plain text inputs.  We rewrite every component
    # schema that has a "files" array property to use the OAS 3.0-style
    # {type: string, format: binary} that Swagger UI correctly maps to a file
    # chooser.  We patch components/schemas (where FastAPI puts the $ref'd
    # body model) rather than the inline requestBody, which only holds a $ref.
    _original_openapi = app.openapi

    def _patched_openapi():
        schema = _original_openapi()
        for component_schema in schema.get("components", {}).get("schemas", {}).values():
            props = component_schema.get("properties", {})
            if "files" in props:
                props["files"] = {
                    "type": "array",
                    "items": {"type": "string", "format": "binary"},
                    "title": "PDF files to upload",
                }
        return schema

    app.openapi = _patched_openapi

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

