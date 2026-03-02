"""TraceLit — v1 Settings Router.

Endpoints for runtime configuration:
- LLM mode toggle (cloud vs local Ollama)
- Provider health status
- Active configuration view
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class LLMModeRequest(BaseModel):
    """Request to switch LLM mode."""
    mode: str  # "cloud" | "local"


class ProviderStatus(BaseModel):
    """Status of a single LLM provider."""
    name: str
    available: bool
    disabled: bool = False
    rate_limited: bool = False


class LLMStatusResponse(BaseModel):
    """Current LLM configuration status."""
    mode: str
    providers: List[ProviderStatus]
    active_provider: Optional[str] = None


# ============================================================
# LLM Mode Toggle
# ============================================================

@router.get("/settings/llm")
async def get_llm_status() -> LLMStatusResponse:
    """Get current LLM configuration and provider status."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    mode = "local" if llm.local_mode else "cloud"

    providers = []
    available = llm._get_available_providers()
    available_names = {p.name for p in available}

    for provider in llm._providers:
        providers.append(ProviderStatus(
            name=provider.name,
            available=provider.name in available_names,
            disabled=provider.name in llm._disabled_providers,
            rate_limited=provider.name in llm._rate_limit_until,
        ))

    return LLMStatusResponse(
        mode=mode,
        providers=providers,
    )


@router.post("/settings/llm")
async def set_llm_mode(request: LLMModeRequest):
    """Switch LLM mode between cloud and local (Ollama).

    - "cloud": Gemini → Groq → Ollama fallback chain
    - "local": Ollama → Gemini → Groq fallback chain (prefer local)
    """
    if request.mode not in ("cloud", "local"):
        raise HTTPException(status_code=400, detail="Mode must be 'cloud' or 'local'")

    from infrastructure.llm.fallback_chain import get_llm, _llm_instance
    import infrastructure.llm.fallback_chain as fc

    old_llm = get_llm()
    local_mode = request.mode == "local"

    if old_llm.local_mode == local_mode:
        return {
            "status": "unchanged",
            "mode": request.mode,
            "detail": f"Already in {request.mode} mode",
        }

    # Shutdown existing instance
    await old_llm.shutdown()

    # Create new instance with the new mode
    from infrastructure.llm.fallback_chain import RobustMultiProviderLLM
    new_llm = RobustMultiProviderLLM(local_mode=local_mode)

    # Transfer session states
    new_llm._session_states = old_llm._session_states

    # Replace singleton
    fc._llm_instance = new_llm

    return {
        "status": "switched",
        "mode": request.mode,
        "providers": [p.name for p in new_llm._providers],
    }


@router.post("/settings/llm/health")
async def check_provider_health():
    """Run health checks on all LLM providers."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    results = {}

    for provider in llm._providers:
        try:
            healthy = await provider.health_check()
            results[provider.name] = {
                "healthy": healthy,
                "disabled": provider.name in llm._disabled_providers,
            }
        except Exception as e:
            results[provider.name] = {
                "healthy": False,
                "error": str(e),
                "disabled": provider.name in llm._disabled_providers,
            }

    return {"providers": results}


@router.get("/settings/config")
async def get_config():
    """Get current application configuration (non-sensitive values)."""
    from app.config import settings

    return {
        "models": {
            "embedding_model": settings.embedding_model,
            "cross_encoder_model": settings.cross_encoder_model,
            "gemini_model": settings.gemini_model,
            "groq_model": settings.groq_model,
        },
        "thresholds": {
            "high_confidence": settings.high_confidence_threshold,
            "medium_confidence": settings.medium_confidence_threshold,
        },
        "limits": {
            "max_papers": settings.max_papers,
            "max_upload_size_mb": settings.max_upload_size_mb,
            "max_concurrent_papers": settings.max_concurrent_papers,
            "max_conversation_turns": settings.max_conversation_turns,
        },
        "llm": {
            "timeout": settings.llm_timeout,
            "temperature": settings.llm_temperature,
        },
    }


@router.get("/settings/memory")
async def get_memory_status():
    """Get current memory usage and status."""
    from shared.memory_monitor import get_memory_monitor
    return get_memory_monitor().check_memory()


@router.get("/settings/rate-limits")
async def get_rate_limit_status():
    """Get current rate limit usage across all providers."""
    from shared.rate_limit_monitor import get_rate_limit_monitor
    return get_rate_limit_monitor().get_all_usage()
