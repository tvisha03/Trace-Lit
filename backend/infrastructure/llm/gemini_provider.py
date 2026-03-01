"""
Gemini 2.0 Flash provider — primary LLM (250K TPM, highest quality).
"""

import asyncio
from typing import AsyncGenerator

import google.generativeai as genai

from infrastructure.llm.base import BaseLLMProvider
from shared.enums import LLMProvider
from shared.errors import RateLimitError, ProviderTimeoutError, EmptyResponseError
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    provider = LLMProvider.GEMINI

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.GEMINI_API_KEY
        self._timeout = settings.LLM_TIMEOUT
        self._configured = False

    def _ensure_configured(self) -> None:
        if not self._configured and self._api_key:
            genai.configure(api_key=self._api_key)
            self._configured = True

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        self._ensure_configured()
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, user_prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ProviderTimeoutError("gemini", self._timeout)
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                raise RateLimitError("gemini")
            raise

        text = response.text.strip() if response.text else ""
        if not text:
            raise EmptyResponseError("gemini")
        return text

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        self._ensure_configured()
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        try:
            response = await asyncio.to_thread(
                model.generate_content, user_prompt, stream=True
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                raise RateLimitError("gemini")
            raise

    async def health_check(self) -> bool:
        return bool(self._api_key)
