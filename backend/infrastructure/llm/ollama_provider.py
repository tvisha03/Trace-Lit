from __future__ import annotations

import base64
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

class OllamaProvider(BaseLLMProvider):
    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.OLLAMA_MODEL
        self._keep_alive = settings.OLLAMA_KEEP_ALIVE
        self._num_ctx = settings.OLLAMA_NUM_CTX
        self._num_threads = settings.OLLAMA_NUM_THREADS
        self._max_tokens = settings.OLLAMA_MAX_TOKENS
        self._httpx_timeout = httpx.Timeout(
            connect=10.0,
            read=float(settings.OLLAMA_TIMEOUT),
            write=10.0,
            pool=5.0,
        )

    def _build_options(self, temperature: float, max_tokens: int) -> dict:
        capped_tokens = min(max_tokens, self._max_tokens)
        opts: dict = {
            "temperature": temperature,
            "num_predict": capped_tokens,
            "num_ctx": self._num_ctx,
        }
        if self._num_threads > 0:
            opts["num_thread"] = self._num_threads
        return opts

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
            "keep_alive": self._keep_alive,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                if resp.status_code == 429:
                    raise RateLimitError("ollama")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
        except RateLimitError:
            raise
        except Exception:
            raise

        text = _strip_think_blocks(data.get("response") or "")
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
            "think": False,
            "keep_alive": self._keep_alive,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/generate", json=payload
                ) as resp:
                    if resp.status_code == 429:
                        raise RateLimitError("ollama")
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
        except RateLimitError:
            raise

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        b64_image = base64.b64encode(image_data).decode("utf-8")
        payload = {
            "model": self._model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                if resp.status_code == 429:
                    raise RateLimitError("ollama")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
        except RateLimitError:
            raise
        except Exception:
            raise

        text = _strip_think_blocks(data.get("response") or "")
        if not text:
            raise EmptyResponseError("ollama")
        return text

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                data = resp.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]
                if any(self._model in name for name in model_names):
                    return True
                logger.warning(
                    f"Ollama server is up but model '{self._model}' not found. "
                    f"Available models: {model_names}"
                )
                return False
        except Exception:
            return False

