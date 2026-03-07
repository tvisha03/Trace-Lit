
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from shared.enums import LLMProvider

class BaseLLMProvider(ABC):

    provider: LLMProvider

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        ...

    @abstractmethod
    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        return
        yield

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        raise NotImplementedError(
            f"{self.provider.value} does not support image analysis"
        )

    async def analyze_images_batch(
        self,
        images: list[tuple[bytes, str]],
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Analyze multiple images in a single API call.

        Args:
            images: List of (image_data, mime_type) tuples.
            prompt: The multi-image prompt (should reference figures by number).
            temperature: Sampling temperature.
            max_tokens: Max output tokens (scaled for multiple figures).

        Returns:
            Raw text response containing analysis for all images.
        """
        raise NotImplementedError(
            f"{self.provider.value} does not support batch image analysis"
        )

