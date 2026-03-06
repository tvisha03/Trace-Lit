"""Ollama Cloud provider — calls Ollama's hosted cloud API at https://ollama.com."""

from __future__ import annotations

import json
import re
from typing import AsyncGenerator

import httpx

from infrastructure.llm.base import BaseLLMProvider
from shared.enums import LLMProvider
from shared.errors import ProviderTimeoutError, EmptyResponseError, RateLimitError
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


class OllamaCloudProvider(BaseLLMProvider):
    """LLM provider that calls Ollama's cloud API directly (https://ollama.com)."""

    provider = LLMProvider.OLLAMA_CLOUD

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.OLLAMA_API_KEY
        self._model = settings.OLLAMA_CLOUD_MODEL
        self._base_url = "https://ollama.com"
        self._max_tokens = settings.OLLAMA_CLOUD_MAX_TOKENS
        self._num_ctx = settings.OLLAMA_CLOUD_NUM_CTX
        self._httpx_timeout = httpx.Timeout(
            connect=15.0,
            read=float(settings.OLLAMA_CLOUD_TIMEOUT),
            write=15.0,
            pool=10.0,
        )
        logger.info(f"Ollama Cloud model: {self._model}")

    def _auth_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _build_options(self, temperature: float, max_tokens: int) -> dict:
        capped_tokens = min(max_tokens, self._max_tokens)
        return {
            "temperature": temperature,
            "num_predict": capped_tokens,
            "num_ctx": self._num_ctx,
        }

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
            "think": False,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._httpx_timeout,
                headers=self._auth_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate", json=payload
                )
                if resp.status_code == 429:
                    raise RateLimitError("ollama_cloud")
                if resp.status_code == 401:
                    logger.error("Ollama Cloud auth failed — check OLLAMA_API_KEY")
                    raise EmptyResponseError("ollama_cloud")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama_cloud", self._httpx_timeout.read)
        except (RateLimitError, EmptyResponseError):
            raise
        except Exception:
            raise

        text = _strip_think_blocks(data.get("response") or "")
        if not text:
            raise EmptyResponseError("ollama_cloud")
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
            "think": False,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._httpx_timeout,
                headers=self._auth_headers(),
            ) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/generate", json=payload
                ) as resp:
                    if resp.status_code == 429:
                        raise RateLimitError("ollama_cloud")
                    if resp.status_code == 401:
                        logger.error("Ollama Cloud auth failed — check OLLAMA_API_KEY")
                        return
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama_cloud", self._httpx_timeout.read)
        except RateLimitError:
            raise

    async def health_check(self) -> bool:
        if not self._api_key:
            logger.warning("Ollama Cloud: no OLLAMA_API_KEY configured")
            return False
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers=self._auth_headers(),
            ) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
