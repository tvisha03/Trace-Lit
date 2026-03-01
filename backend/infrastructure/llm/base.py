"""TraceLit — Abstract LLM Provider Base."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        ...

    async def health_check(self) -> bool:
        try:
            response = await self.generate(
                system_prompt="Reply with OK.",
                user_prompt="Health check.",
                max_tokens=10,
            )
            return bool(response)
        except Exception:
            return False
