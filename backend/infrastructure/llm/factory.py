"""
Provider factory — builds the correct LLM provider instance by name.
"""

from shared.enums import LLMProvider
from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.gemini_provider import GeminiProvider
from infrastructure.llm.groq_provider import GroqProvider
from infrastructure.llm.ollama_provider import OllamaProvider


_REGISTRY: dict[LLMProvider, type[BaseLLMProvider]] = {
    LLMProvider.GEMINI: GeminiProvider,
    LLMProvider.GROQ: GroqProvider,
    LLMProvider.OLLAMA: OllamaProvider,
}


def create_provider(provider: LLMProvider) -> BaseLLMProvider:
    """Instantiate the requested LLM provider."""
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return cls()
