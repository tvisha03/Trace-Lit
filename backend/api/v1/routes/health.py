
from fastapi import APIRouter, Request
from sqlalchemy import text

from api.v1.schemas import HealthResponse
from app.config import get_settings
from infrastructure.db.database import async_session_factory
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _check_cross_encoder() -> bool:
    try:
        from domain.verification.reranker import _get_cross_encoder
        return _get_cross_encoder() is not None
    except Exception:
        return False


def _check_faiss(request) -> tuple[bool, dict | None]:
    faiss_store = getattr(request.app.state, "faiss_store", None)
    if faiss_store is None:
        return False, None
    try:
        ok = faiss_store.is_ready()
        stats = faiss_store.get_stats() if ok else None
        return ok, stats
    except Exception as exc:
        logger.warning(f"Health check: FAISS status check failed: {exc}")
        return False, None


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

    db_ok = False
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning(f"Health check: DB connectivity failed: {exc}")

    faiss_ok, faiss_stats = _check_faiss(request)

    overall = "ok" if db_ok else "degraded"

    cross_encoder_ok = _check_cross_encoder()
    if not cross_encoder_ok:
        logger.warning(
            "Health check: cross-encoder model unavailable — "
            "HAVF verification will use Level 1 (embedding) only. "
            "Run scripts/download_models.py to enable Level 2 reranking."
        )
        if overall == "ok":
            overall = "degraded"

    return HealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        providers=providers,
        db=db_ok,
        faiss=faiss_ok,
        faiss_stats=faiss_stats,
        cross_encoder=cross_encoder_ok,
    )

