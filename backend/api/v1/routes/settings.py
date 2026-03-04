
from fastapi import APIRouter, Request
from pydantic import BaseModel

from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# FIXED CRT-003: Runtime configuration stored separately from Settings singleton
# This prevents mutation of the cached singleton and provides thread-safe runtime config
class RuntimeConfig:
    """Thread-safe runtime configuration that persists across requests."""
    
    def __init__(self):
        self._use_local_llm: bool = False
    
    @property
    def use_local_llm(self) -> bool:
        return self._use_local_llm
    
    @use_local_llm.setter
    def use_local_llm(self, value: bool) -> None:
        self._use_local_llm = value
    
    def get_provider_order(self) -> list[str]:
        if self._use_local_llm:
            return ["ollama", "gemini", "groq"]
        return ["gemini", "groq", "ollama"]

# Global runtime config instance - survives across requests
_runtime_config = RuntimeConfig()


class OllamaToggleRequest(BaseModel):
    use_local_llm: bool


class OllamaToggleResponse(BaseModel):
    use_local_llm: bool
    provider_order: list[str]


@router.get("/ollama", response_model=OllamaToggleResponse)
async def get_ollama_status(request: Request):
    llm = getattr(request.app.state, "llm", None)
    provider_order = (
        [p.provider.value for p in llm.providers] if llm else []
    )
    return OllamaToggleResponse(
        use_local_llm=_runtime_config.use_local_llm,
        provider_order=provider_order,
    )


@router.put("/ollama", response_model=OllamaToggleResponse)
async def toggle_ollama(request: Request, body: OllamaToggleRequest):
    # FIXED CRT-003: Use runtime config instead of mutating singleton
    _runtime_config.use_local_llm = body.use_local_llm

    llm = getattr(request.app.state, "llm", None)
    if llm is not None:
        llm._providers = llm._build_chain()
        logger.info(
            f"Ollama toggle: USE_LOCAL_LLM={body.use_local_llm}, "
            f"provider order={[p.provider.value for p in llm.providers]}"
        )

    provider_order = (
        [p.provider.value for p in llm.providers] if llm else []
    )

    return OllamaToggleResponse(
        use_local_llm=body.use_local_llm,
        provider_order=provider_order,
    )
