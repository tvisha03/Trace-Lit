from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.lifespan import lifespan
from api.v1.router import api_v1_router
from api.v1.routes.websocket import router as ws_router

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

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    # WebSocket routes are mounted at the app root (no versioning) so the frontend
    # can connect via ws://host/ws/{session_id} without a versioned prefix.
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

    return app

app = create_app()
