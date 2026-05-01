
from fastapi import APIRouter, Request
from pydantic import BaseModel
import asyncio

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

        provider_order = (
            [p.provider.value for p in llm.providers] if llm else []
        )

    return OllamaToggleResponse(
        use_local_llm=body.use_local_llm,
        provider_order=provider_order,
    )
