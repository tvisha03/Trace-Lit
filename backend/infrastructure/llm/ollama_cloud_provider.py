"""Ollama Cloud provider — calls Ollama's hosted cloud API at https://ollama.com."""

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


def _extract_chat_text(data: dict) -> str:
    message = data.get("message") or {}
    content = message.get("content") or data.get("response") or ""
    return _strip_think_blocks(content)


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

    def _candidate_models(self, model: str) -> list[str]:
        if model.endswith(":cloud"):
            return [model, model.removesuffix(":cloud")]
        return [model]

    def _build_text_messages(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _log_missing_model(self, model: str, *, vision: bool = False) -> None:
        kind = "vision model" if vision else "model"
        logger.warning(
            "Ollama Cloud %s '%s' returned 404 on /api/chat; trying next alias",
            kind,
            model,
        )

    def _build_chat_payload(
        self,
        model: str,
        messages: list[dict[str, object]],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, object]:
        return {
            "model": model,
            "messages": messages,
            "stream": stream,
            "think": False,
            "options": self._build_options(temperature, max_tokens),
        }

    def _check_chat_response_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimitError("ollama_cloud")
        if resp.status_code == 401:
            logger.error("Ollama Cloud auth failed — check OLLAMA_API_KEY")
            raise EmptyResponseError("ollama_cloud")
        resp.raise_for_status()

    def _extract_stream_token(self, line: str) -> str:
        if not line:
            return ""
        chunk = json.loads(line)
        return (chunk.get("message") or {}).get("content", "")

    async def _post_chat(self, payload: dict[str, object]) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=self._httpx_timeout,
                headers=self._auth_headers(),
            ) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                self._check_chat_response_status(resp)
                return resp.json()
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama_cloud", self._httpx_timeout.read)
        except (RateLimitError, EmptyResponseError):
            raise

    async def _generate_via_chat(
        self,
        model: str,
        messages: list[dict[str, object]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = self._build_chat_payload(
            model, messages, temperature, max_tokens, stream=False
        )
        data = await self._post_chat(payload)
        text = _extract_chat_text(data)
        if not text:
            raise EmptyResponseError("ollama_cloud")
        return text

    async def _stream_via_chat(
        self,
        model: str,
        messages: list[dict[str, object]],
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_chat_payload(
            model, messages, temperature, max_tokens, stream=True
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._httpx_timeout,
                headers=self._auth_headers(),
            ) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/chat", json=payload
                ) as resp:
                    self._check_chat_response_status(resp)
                    async for line in resp.aiter_lines():
                        token = self._extract_stream_token(line)
                        if token:
                            yield token
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama_cloud", self._httpx_timeout.read)
        except (RateLimitError, EmptyResponseError):
            raise

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        messages = self._build_text_messages(system_prompt, user_prompt)

        last_404: httpx.HTTPStatusError | None = None
        for model in self._candidate_models(self._model):
            try:
                return await self._generate_via_chat(
                    model, messages, temperature, max_tokens
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                last_404 = exc
                self._log_missing_model(model)

        if last_404 is not None:
            raise EmptyResponseError("ollama_cloud")
        raise EmptyResponseError("ollama_cloud")

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        messages = self._build_text_messages(system_prompt, user_prompt)

        last_404: httpx.HTTPStatusError | None = None
        for model in self._candidate_models(self._model):
            try:
                async for token in self._stream_via_chat(
                    model, messages, temperature, max_tokens
                ):
                    yield token
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                last_404 = exc
                self._log_missing_model(model)

        if last_404 is not None:
            raise EmptyResponseError("ollama_cloud")

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

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Analyze an image using Ollama Cloud with a vision-capable model."""
        vision_model = get_settings().OLLAMA_CLOUD_VISION_MODEL
        b64_image = base64.b64encode(image_data).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ]

        last_404: httpx.HTTPStatusError | None = None
        for model in self._candidate_models(vision_model):
            try:
                return await self._generate_via_chat(
                    model, messages, temperature, max_tokens
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                last_404 = exc
                self._log_missing_model(model, vision=True)

        if last_404 is not None:
            raise EmptyResponseError("ollama_cloud")
        raise EmptyResponseError("ollama_cloud")
