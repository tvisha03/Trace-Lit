
from shared.enums import LLMProvider
from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.gemini_provider import GeminiProvider
from infrastructure.llm.groq_provider import GroqProvider
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.llm.ollama_cloud_provider import OllamaCloudProvider

_REGISTRY: dict[LLMProvider, type[BaseLLMProvider]] = {
    LLMProvider.GEMINI: GeminiProvider,
    LLMProvider.GROQ: GroqProvider,
    LLMProvider.OLLAMA: OllamaProvider,
    LLMProvider.OLLAMA_CLOUD: OllamaCloudProvider,
}

def create_provider(provider: LLMProvider) -> BaseLLMProvider:
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return cls()

