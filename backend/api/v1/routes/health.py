"""
Health check route.
"""

from fastapi import APIRouter, Request

from api.v1.schemas import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check(request: Request):
    """Return service health status and active LLM provider availability."""
    providers = {}
    llm = getattr(request.app.state, "llm", None)
    if llm:
        for provider in llm.providers:
            try:
                ok = await provider.health_check()
                providers[provider.__class__.__name__] = ok
            except Exception:
                providers[provider.__class__.__name__] = False

    return HealthResponse(
        status="ok",
        version="0.1.0",
        providers=providers,
    )
