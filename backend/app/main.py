"""TraceLit — FastAPI Application Entry Point.

Configures middleware, exception handlers, and router registration.
Startup / shutdown logic lives in app.lifespan.
"""

import os

# Runtime stability on Apple Silicon (FAISS/OpenMP + PyTorch MPS).
# Must be set before any native library is imported.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import psutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.lifespan import lifespan
from shared.constants import STATUS_CODE_MAP
from shared.errors import TraceLitError


# ============================================================
# App Instance
# ============================================================

app = FastAPI(
    title="TraceLit",
    description="AI-Powered Research Paper Analysis with Sentence-Level Attribution",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# Middleware
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Global Exception Handlers
# ============================================================

@app.exception_handler(TraceLitError)
async def tracelit_error_handler(request: Request, exc: TraceLitError) -> JSONResponse:
    """Handle all custom TraceLit exceptions with structured JSON responses."""
    logger.warning(f"TraceLit error: {exc.code} — {exc.message}")
    status_code = STATUS_CODE_MAP.get(exc.code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "status": "error",
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors — never expose raw stack traces."""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": {},
            },
            "status": "error",
        },
    )


# ============================================================
# Health Check
# ============================================================

from pydantic import BaseModel
from typing import Dict, Optional


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    memory_used_gb: float = 0.0
    faiss: str = "not_initialized"
    models_loaded: Dict[str, bool] = {}


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """System health check with memory and service status."""
    mem = psutil.virtual_memory()

    faiss_status = "not_initialized"
    try:
        from infrastructure.vector_store.faiss_store import get_vector_store
        doc_count = get_vector_store().count()
        faiss_status = f"ready ({doc_count} docs)"
    except Exception:
        faiss_status = "error"

    embedding_loaded = False
    cross_encoder_loaded = False
    try:
        from infrastructure.vector_store.faiss_store import get_embedder
        embedding_loaded = get_embedder().is_loaded()
    except Exception:
        pass
    try:
        from domain.verification.havf import get_havf
        cross_encoder_loaded = get_havf()._cross_encoder is not None
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        memory_used_gb=round(mem.used / (1024**3), 2),
        faiss=faiss_status,
        models_loaded={
            "embedding": embedding_loaded,
            "cross_encoder": cross_encoder_loaded,
        },
    )


# ============================================================
# Router Registration
# ============================================================

from api.v1.router import router as v1_router
from api.v1.websocket.router import router as ws_router

app.include_router(v1_router, prefix="/api/v1")
app.include_router(ws_router)  # WebSocket at root level: /ws/papers/progress

# ─── Legacy unversioned prefix (keeps existing frontend working) ────────────
from api.v1.papers.router import router as papers_router
from api.v1.sessions.router import router as sessions_router
from api.v1.chat.router import router as chat_router
from api.v1.comparison.router import router as compare_router
from api.v1.export.router import router as export_router

app.include_router(papers_router,  prefix="/api", tags=["Papers (legacy)"])
app.include_router(sessions_router, prefix="/api", tags=["Sessions (legacy)"])
app.include_router(chat_router,    prefix="/api", tags=["Chat (legacy)"])
app.include_router(compare_router, prefix="/api", tags=["Comparison (legacy)"])
app.include_router(export_router,  prefix="/api", tags=["Export (legacy)"])

