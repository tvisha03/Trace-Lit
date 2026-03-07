
from fastapi import APIRouter, Request
from pydantic import BaseModel
import asyncio
import httpx

from app.config import get_settings
from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_toggle_lock = asyncio.Lock()

class RuntimeConfig:
    def __init__(self):
        from app.config import get_settings
        self._use_local_llm: bool = get_settings().USE_LOCAL_LLM

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

_runtime_config = RuntimeConfig()

class OllamaToggleRequest(BaseModel):
    use_local_llm: bool

class OllamaToggleResponse(BaseModel):
    use_local_llm: bool
    provider_order: list[str]

async def _unload_ollama_model() -> None:
    """Tell Ollama to unload the current model by setting keep_alive to 0.

    Frees 2-3 GB of RAM when switching to cloud-first mode.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "keep_alive": 0,
                },
                timeout=10.0,
            )
            logger.info(
                f"Unloaded Ollama model '{settings.OLLAMA_MODEL}' to free GPU/RAM"
            )
    except Exception as exc:
        logger.warning(f"Failed to unload Ollama model: {exc}")

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
    async with _toggle_lock:
        _runtime_config.use_local_llm = body.use_local_llm

        llm = getattr(request.app.state, "llm", None)
        if llm is not None:
            new_chain = llm._build_chain(use_local_llm=body.use_local_llm)
            llm._providers = new_chain
            logger.info(
                f"Ollama toggle: USE_LOCAL_LLM={body.use_local_llm}, "
                f"provider order={[p.provider.value for p in llm.providers]}"
            )

        # Unload Ollama model from RAM/GPU when switching to cloud-first
        if not body.use_local_llm:
            await _unload_ollama_model()

        provider_order = (
            [p.provider.value for p in llm.providers] if llm else []
        )

    return OllamaToggleResponse(
        use_local_llm=body.use_local_llm,
        provider_order=provider_order,
    )
