"""TraceLit — LLM Provider Factory.

Instantiates providers based on available API keys and mode.
"""

from typing import List

from app.config import settings
from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.gemini_provider import GeminiClient
from infrastructure.llm.groq_provider import GroqClient
from infrastructure.llm.ollama_provider import OllamaClient


def build_provider_chain(local_mode: bool = False) -> List[BaseLLMProvider]:
    """Build the ordered provider list for the fallback chain.

    Cloud mode  : Gemini → Groq → Ollama
    Local mode  : Ollama → Gemini → Groq

    Args:
        local_mode: Prefer local Ollama over cloud providers.

    Returns:
        Ordered list of initialised providers.
    """
    gemini = GeminiClient() if settings.gemini_api_key else None
    groq = GroqClient() if settings.groq_api_key else None
    ollama = OllamaClient()

    if local_mode:
        chain = [ollama]
        if gemini:
            chain.append(gemini)
        if groq:
            chain.append(groq)
    else:
        chain = []
        if gemini:
            chain.append(gemini)
        if groq:
            chain.append(groq)
        chain.append(ollama)

    return chain
