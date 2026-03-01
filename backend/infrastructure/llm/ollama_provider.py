"""TraceLit — Ollama local provider."""

import json
from typing import AsyncIterator, Optional

import httpx
from loguru import logger

from app.config import settings
from infrastructure.llm.base import BaseLLMProvider
from shared.errors import ProviderError


class OllamaClient(BaseLLMProvider):
    """Local Ollama via HTTP API."""

    name = "ollama"
    model = "llama3.2:3b"

    def __init__(self, base_url: str = "http://localhost:11434", model: Optional[str] = None):
        self.base_url = base_url
        if model:
            self.model = model
        self._http_client: Optional[httpx.AsyncClient] = None

    def _ensure_client(self) -> None:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(settings.llm_timeout, connect=5.0),
            )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        self._ensure_client()
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            response = await self._http_client.post("/api/generate", json=payload)
            response.raise_for_status()
            text = response.json().get("response", "")
            if not text:
                raise ProviderError(message="Ollama returned empty response", code="EMPTY_RESPONSE", details={"provider": self.name})
            return text
        except httpx.ConnectError:
            raise ProviderError(message="Ollama is not running (connection refused)", code="PROVIDER_UNAVAILABLE", details={"provider": self.name, "url": self.base_url})
        except httpx.TimeoutException:
            raise ProviderError(message=f"Ollama timeout after {settings.llm_timeout}s", code="TIMEOUT", details={"provider": self.name})
        except httpx.HTTPStatusError as e:
            raise ProviderError(message=f"Ollama HTTP error: {e.response.status_code}", code="PROVIDER_ERROR", details={"provider": self.name})
        except Exception as e:
            raise ProviderError(message=f"Ollama error: {e}", code="PROVIDER_ERROR", details={"provider": self.name})

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        self._ensure_client()
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with self._http_client.stream("POST", "/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break
        except httpx.ConnectError:
            raise ProviderError(message="Ollama is not running", code="PROVIDER_UNAVAILABLE", details={"provider": self.name})
        except Exception as e:
            raise ProviderError(message=f"Ollama stream error: {e}", code="STREAM_ERROR", details={"provider": self.name})

    async def health_check(self) -> bool:
        self._ensure_client()
        try:
            resp = await self._http_client.get("/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return any(self.model in m.get("name", "") for m in models)
            return False
        except Exception:
            return False

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
