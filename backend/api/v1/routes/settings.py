
from fastapi import APIRouter, Request
from pydantic import BaseModel

from shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


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
    from app.config import get_settings
    settings = get_settings()
    return OllamaToggleResponse(
        use_local_llm=settings.USE_LOCAL_LLM,
        provider_order=provider_order,
    )


@router.put("/ollama", response_model=OllamaToggleResponse)
async def toggle_ollama(request: Request, body: OllamaToggleRequest):
    from app.config import get_settings
    settings = get_settings()

    settings.USE_LOCAL_LLM = body.use_local_llm

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

