"""TraceLit — FastAPI Application Entry Point.

Configures middleware, exception handlers, startup events, and router registration.
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# --- Runtime stability on Apple Silicon (FAISS/OpenMP + PyTorch MPS) ---
# Must be set before any native library is imported.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import psutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.exceptions import TraceLitError
from app.schemas.api_schemas import HealthResponse


# ============================================================
# Logging Configuration
# ============================================================

def _configure_logging() -> None:
    """Set up loguru with console + rotating file handlers."""
    logger.remove()  # Remove default handler

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
    )

    # Ensure log directory exists
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        settings.log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="5 days",
        compression="zip",
        format="{time} | {level} | {name}:{function}:{line} | {message}",
    )


# ============================================================
# Lifespan (Startup / Shutdown)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # --- Startup ---
    _configure_logging()
    logger.info("TraceLit backend starting up...")

    settings.ensure_directories()
    logger.info("Data directories verified")

    from app.models.database import init_db
    init_db()
    logger.info("Database initialized")

    logger.info("TraceLit backend ready")

    yield

    # --- Shutdown ---
    logger.info("TraceLit backend shutting down...")


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

_STATUS_CODE_MAP = {
    "RATE_LIMIT": 429,
    "ALL_PROVIDERS_FAILED": 503,
    "INVALID_CITATION": 422,
    "EXTRACTION_FAILED": 500,
    "PAPER_NOT_READY": 409,
    "PAPER_LIMIT_EXCEEDED": 400,
    "FILE_TOO_LARGE": 413,
    "INVALID_FILE": 400,
}


@app.exception_handler(TraceLitError)
async def tracelit_error_handler(request: Request, exc: TraceLitError) -> JSONResponse:
    """Handle all custom TraceLit exceptions with structured JSON responses."""
    logger.warning(f"TraceLit error: {exc.code} — {exc.message}")
    status_code = _STATUS_CODE_MAP.get(exc.code, 500)
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

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """System health check with memory and service status."""
    mem = psutil.virtual_memory()

    # Check vector store status
    vector_status = "not_initialized"
    try:
        from app.embeddings.vector_store import get_vector_store
        store = get_vector_store()
        doc_count = store.count()
        vector_status = f"ready ({doc_count} docs)"
    except Exception:
        vector_status = "error"

    # Check model status
    embedding_loaded = False
    cross_encoder_loaded = False
    try:
        from app.embeddings.mps_embedder import get_embedder
        embedding_loaded = get_embedder().is_loaded()
    except Exception:
        pass
    try:
        from app.verification.havf import get_havf
        cross_encoder_loaded = get_havf()._cross_encoder is not None
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        memory_used_gb=round(mem.used / (1024**3), 2),
        chromadb=vector_status,
        models_loaded={
            "embedding": embedding_loaded,
            "cross_encoder": cross_encoder_loaded,
        },
    )


# ============================================================
# Router Registration
# ============================================================

from app.api.papers import router as papers_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.compare import router as compare_router
from app.api.export import router as export_router

app.include_router(papers_router, prefix="/api", tags=["Papers"])
app.include_router(sessions_router, prefix="/api", tags=["Sessions"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(compare_router, prefix="/api", tags=["Comparison"])
app.include_router(export_router, prefix="/api", tags=["Export"])
