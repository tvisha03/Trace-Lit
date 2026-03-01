"""
Abstract base for all LLM providers.
Concrete providers implement generate() and generate_streaming().
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from shared.enums import LLMProvider


class BaseLLMProvider(ABC):
    """Interface that every LLM provider must satisfy."""

    provider: LLMProvider

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Return the complete generated text."""
        ...

    @abstractmethod
    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Yield incremental token chunks."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable and has available quota."""
        ...
