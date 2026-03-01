"""TraceLit — Groq Llama 3.1 70B provider."""

import asyncio
from typing import AsyncIterator, Optional

from loguru import logger

from app.config import settings
from infrastructure.llm.base import BaseLLMProvider
from shared.errors import ProviderError, RateLimitError


class GroqClient(BaseLLMProvider):
    """Groq-hosted Llama 3.1 70B via groq SDK."""

    name = "groq"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = settings.groq_model
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
                logger.info(f"Groq client initialised (model={self.model})")
            except Exception as e:
                raise ProviderError(message=f"Failed to initialise Groq: {e}", code="PROVIDER_INIT_ERROR", details={"provider": self.name})

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        self._ensure_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=self.model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                ),
                timeout=settings.llm_timeout,
            )
            text = response.choices[0].message.content
            if not text:
                raise ProviderError(message="Groq returned empty response", code="EMPTY_RESPONSE", details={"provider": self.name})
            return text
        except asyncio.TimeoutError:
            raise ProviderError(message=f"Groq timeout after {settings.llm_timeout}s", code="TIMEOUT", details={"provider": self.name})
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                raise RateLimitError(provider=self.name, retry_after=60)
            if "api key" in err or "authentication" in err:
                raise ProviderError(message=f"Groq auth error: {e}", code="AUTH_ERROR", details={"provider": self.name})
            raise ProviderError(message=f"Groq error: {e}", code="PROVIDER_ERROR", details={"provider": self.name})

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        self._ensure_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self.model, messages=messages,
                temperature=temperature, max_tokens=max_tokens, stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                raise RateLimitError(provider=self.name, retry_after=60)
            raise ProviderError(message=f"Groq stream error: {e}", code="STREAM_ERROR", details={"provider": self.name})
