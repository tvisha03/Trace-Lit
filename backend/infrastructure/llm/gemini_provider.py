
from __future__ import annotations

from typing import AsyncGenerator

from google import genai
from google.genai import types

from infrastructure.llm.base import BaseLLMProvider
from shared.enums import LLMProvider
from shared.errors import RateLimitError, ProviderTimeoutError, EmptyResponseError
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)

_MODEL = "gemini-2.5-flash"

class GeminiProvider(BaseLLMProvider):
    provider = LLMProvider.GEMINI

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.GEMINI_API_KEY
        self._timeout = settings.LLM_TIMEOUT
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        try:
            response = await client.aio.models.generate_content(
                model=_MODEL,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                raise RateLimitError("gemini")
            if "timeout" in exc_str.lower() or "deadline" in exc_str.lower():
                raise ProviderTimeoutError("gemini", self._timeout)
            raise

        text = (response.text or "").strip()
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
        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        try:
            async for chunk in client.aio.models.generate_content_stream(
                model=_MODEL,
                contents=user_prompt,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                raise RateLimitError("gemini")
            if "timeout" in exc_str.lower() or "deadline" in exc_str.lower():
                raise ProviderTimeoutError("gemini", self._timeout)
            raise

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            client = self._get_client()
            await client.aio.models.get(model=_MODEL)
            return True
        except Exception:
            return False

