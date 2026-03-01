"""
Groq provider — fast, configurable model (defaults to mixtral-8x7b-32768).
Model can be overridden via GROQ_MODEL environment variable.
"""

import asyncio
from typing import AsyncGenerator

from groq import AsyncGroq

from infrastructure.llm.base import BaseLLMProvider
from shared.enums import LLMProvider
from shared.errors import RateLimitError, ProviderTimeoutError, EmptyResponseError
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)


class GroqProvider(BaseLLMProvider):
    provider = LLMProvider.GROQ

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.GROQ_API_KEY
        self._model = settings.GROQ_MODEL
        self._timeout = settings.LLM_TIMEOUT
        self._client: AsyncGroq | None = None

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        client = self._get_client()
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ProviderTimeoutError("groq", self._timeout)
        except Exception as exc:
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                raise RateLimitError("groq")
            raise

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise EmptyResponseError("groq")
        return text

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        client = self._get_client()
        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ProviderTimeoutError("groq", self._timeout)
        except Exception as exc:
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                raise RateLimitError("groq")
            raise

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def health_check(self) -> bool:
        return bool(self._api_key)
