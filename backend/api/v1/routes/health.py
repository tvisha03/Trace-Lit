
from fastapi import APIRouter, Request
from sqlalchemy import text

from api.v1.schemas import HealthResponse
from app.config import get_settings
from infrastructure.db.database import async_session_factory
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.get("", response_model=HealthResponse)
async def health_check(request: Request):
    settings = get_settings()
    providers = {}
    llm = getattr(request.app.state, "llm", None)
    if llm:
        for provider in llm.providers:
            try:
                ok = await provider.health_check()
                providers[provider.__class__.__name__] = ok
            except Exception:
                providers[provider.__class__.__name__] = False

    # Verify database connectivity with a lightweight round-trip query.
    db_ok = False
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning(f"Health check: DB connectivity failed: {exc}")

    # Verify the FAISS index is loaded and contains at least 0 vectors.
    faiss_ok = False
    faiss_store = getattr(request.app.state, "faiss_store", None)
    if faiss_store is not None:
        try:
            faiss_ok = faiss_store.is_ready()
        except Exception as exc:
            logger.warning(f"Health check: FAISS status check failed: {exc}")

    overall = "ok" if db_ok else "degraded"

    return HealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        providers=providers,
        db=db_ok,
        faiss=faiss_ok,
    )
