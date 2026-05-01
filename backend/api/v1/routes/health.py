
from fastapi import APIRouter, Request
from sqlalchemy import text

from api.v1.schemas import HealthResponse
from api.v1.routes.settings import _runtime_config
from app.config import get_settings
from infrastructure.db.database import async_session_factory
from shared.enums import LLMProvider
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

async def _check_providers(request: Request) -> dict[str, bool]:
    providers: dict[str, bool] = {}
    llm = getattr(request.app.state, "llm", None)
    if not llm:
        return providers
    for provider in llm.providers:
        if provider.provider == LLMProvider.OLLAMA:
            providers[provider.__class__.__name__] = _runtime_config.use_local_llm
        else:
            try:
                ok = await provider.health_check()
                providers[provider.__class__.__name__] = ok
            except Exception:
                providers[provider.__class__.__name__] = False
    return providers

async def _check_db() -> bool:
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Health check: DB connectivity failed: {exc}")
        return False

def _compute_overall(db_ok: bool, cross_encoder_ok: bool) -> str:
    if not db_ok:
        return "degraded"
    if not cross_encoder_ok:
        logger.warning(
            "Health check: cross-encoder model unavailable — "
            "HAVF verification will use Level 1 (embedding) only. "
            "Run scripts/download_models.py to enable Level 2 reranking."
        )
        return "degraded"
    return "ok"

@router.get("", response_model=HealthResponse)
async def health_check(request: Request):
    settings = get_settings()
    providers = await _check_providers(request)
    db_ok = await _check_db()
    faiss_ok, faiss_stats = _check_faiss(request)
    cross_encoder_ok = _check_cross_encoder()
    overall = _compute_overall(db_ok, cross_encoder_ok)

    llm = getattr(request.app.state, "llm", None)
    provider_order = (
        [p.provider.value for p in llm.providers] if llm else []
    )

    return HealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        use_local_llm=_runtime_config.use_local_llm,
        provider_order=provider_order,
        providers=providers,
        db=db_ok,
        faiss=faiss_ok,
        faiss_stats=faiss_stats,
        cross_encoder=cross_encoder_ok,
    )

