
from __future__ import annotations

from typing import AsyncGenerator

import httpx

from infrastructure.llm.base import BaseLLMProvider
from shared.enums import LLMProvider
from shared.errors import ProviderTimeoutError, EmptyResponseError
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)

class OllamaProvider(BaseLLMProvider):
    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.OLLAMA_MODEL
        self._timeout = settings.LLM_TIMEOUT

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        payload = {
            "model": self._model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._timeout)
        except Exception:
            raise

        text = (data.get("response") or "").strip()
        if not text:
            raise EmptyResponseError("ollama")
        return text

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self._model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/generate", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            import json
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._timeout)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
