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
            or request.url.path.endswith("/stream")
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

