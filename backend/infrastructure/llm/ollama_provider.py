from __future__ import annotations

import asyncio
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

# Connection retry settings for local Ollama resilience
_CONNECT_RETRIES = 2
_CONNECT_RETRY_DELAY = 3.0

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

def _strip_think_blocks(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()

class OllamaProvider(BaseLLMProvider):
    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.OLLAMA_MODEL
        self._vision_model = settings.OLLAMA_VISION_MODEL
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
        self._current_loaded_model: str | None = None
        logger.info(
            f"Ollama models — text: {self._model}, vision: {self._vision_model}"
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

    async def _unload_model(self, model_name: str) -> None:
        """Unload a model from VRAM by setting keep_alive to 0s."""
        payload = {"model": model_name, "keep_alive": "0s"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self._base_url}/api/generate", json=payload)
                logger.debug(f"Unloaded model: {model_name}")
        except Exception as exc:
            logger.debug(f"Unload request failed for {model_name}: {exc}")

    async def _ensure_model_loaded(self, target_model: str) -> None:
        """Unload the other model if loaded, ensuring only target_model is in VRAM."""
        if self._current_loaded_model == target_model:
            return  # Already loaded — no-op
        if self._current_loaded_model and self._current_loaded_model != target_model:
            logger.info(f"Swapping models: {self._current_loaded_model} → {target_model}")
            await self._unload_model(self._current_loaded_model)
        else:
            logger.info(f"Loading model: {target_model}")
        self._current_loaded_model = target_model

    async def _with_connect_retry(self, url: str, payload: dict) -> dict:
        """POST to Ollama with connection retries for local server resilience."""
        for attempt in range(_CONNECT_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 429:
                        raise RateLimitError("ollama")
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.TimeoutException, RateLimitError, EmptyResponseError):
                raise
            except httpx.ConnectError:
                if attempt < _CONNECT_RETRIES:
                    logger.warning(
                        f"Ollama connection failed (attempt {attempt + 1}/{_CONNECT_RETRIES + 1}), "
                        f"retrying in {_CONNECT_RETRY_DELAY}s"
                    )
                    await asyncio.sleep(_CONNECT_RETRY_DELAY)
                    continue
                raise

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        await self._ensure_model_loaded(self._model)
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
            data = await self._with_connect_retry(
                f"{self._base_url}/api/generate", payload
            )
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
        text = _strip_think_blocks(data.get("response") or "")
        if not text:
            raise EmptyResponseError("ollama")
        return text

    async def _stream_tokens(
        self, url: str, payload: dict
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the given Ollama endpoint."""
        async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code == 429:
                    raise RateLimitError("ollama")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        await self._ensure_model_loaded(self._model)
        payload = {
            "model": self._model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": True,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": self._build_options(temperature, max_tokens),
        }
        url = f"{self._base_url}/api/generate"
        for attempt in range(_CONNECT_RETRIES + 1):
            try:
                async for token in self._stream_tokens(url, payload):
                    yield token
                return
            except httpx.TimeoutException:
                raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
            except RateLimitError:
                raise
            except httpx.ConnectError:
                if attempt < _CONNECT_RETRIES:
                    logger.warning(
                        f"Ollama stream connection retry {attempt + 1}/{_CONNECT_RETRIES + 1}"
                    )
                    await asyncio.sleep(_CONNECT_RETRY_DELAY)
                    continue
                raise

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        await self._ensure_model_loaded(self._vision_model)
        b64_image = base64.b64encode(image_data).decode("utf-8")
        payload = {
            "model": self._vision_model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": self._build_options(temperature, max_tokens),
        }
        try:
            data = await self._with_connect_retry(
                f"{self._base_url}/api/generate", payload
            )
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama", self._httpx_timeout.read)
        text = _strip_think_blocks(data.get("response") or "")
        if not text:
            raise EmptyResponseError("ollama")
        return text

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                data = resp.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]
                required = {self._model, self._vision_model}
                found = {
                    req for req in required
                    if any(req in name for name in model_names)
                }
                missing = required - found
                if missing:
                    logger.warning(
                        f"Ollama server is up but missing models: {missing}. "
                        f"Available: {model_names}"
                    )
                    return False
                return True
        except Exception:
            return False

