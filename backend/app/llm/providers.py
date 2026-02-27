"""TraceLit — LLM Provider Clients.

Individual async clients for Gemini 2.0 Flash, Groq Llama 3.1 70B,
and Ollama (local). Each provider implements a common interface.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Optional, Tuple

import httpx
from loguru import logger

from app.config import settings
from app.exceptions import ProviderError, RateLimitError


# ============================================================
# Base Provider Interface
# ============================================================

class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Generate a complete response.

        Args:
            system_prompt: System instructions (citation rules, etc.).
            user_prompt: User question with context.
            temperature: Sampling temperature (low = factual).
            max_tokens: Maximum output tokens.

        Returns:
            Full response text.

        Raises:
            RateLimitError: Provider rate limit hit.
            ProviderError: Other provider-specific error.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        """Stream response tokens.

        Yields:
            Text chunks as they become available.
        """
        ...

    async def health_check(self) -> bool:
        """Verify the provider is reachable.

        Returns:
            True if provider is available.
        """
        try:
            response = await self.generate(
                system_prompt="Reply with OK.",
                user_prompt="Health check.",
                max_tokens=10,
            )
            return bool(response)
        except Exception:
            return False


# ============================================================
# Gemini 2.0 Flash (Primary — 250K TPM free tier)
# ============================================================

class GeminiClient(BaseLLMProvider):
    """Google Gemini 2.0 Flash client via google-generativeai SDK."""

    name = "gemini"
    model = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self._client = None
        self._model = None

    def _ensure_client(self) -> None:
        """Lazy-initialize the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel(self.model)
                self._client = genai
                logger.info(f"Gemini client initialized (model={self.model})")
            except Exception as e:
                raise ProviderError(
                    message=f"Failed to initialize Gemini: {e}",
                    code="PROVIDER_INIT_ERROR",
                    details={"provider": self.name},
                )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Generate response via Gemini API.

        Uses asyncio.to_thread since google-generativeai is sync.
        """
        self._ensure_client()

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._model.generate_content,
                    combined_prompt,
                    generation_config=generation_config,
                ),
                timeout=settings.llm_timeout,
            )

            if not response or not response.text:
                raise ProviderError(
                    message="Gemini returned empty response",
                    code="EMPTY_RESPONSE",
                    details={"provider": self.name},
                )

            logger.debug(f"Gemini response: {len(response.text)} chars")
            return response.text

        except asyncio.TimeoutError:
            logger.warning(f"Gemini timeout after {settings.llm_timeout}s")
            raise ProviderError(
                message=f"Gemini timeout after {settings.llm_timeout}s",
                code="TIMEOUT",
                details={"provider": self.name, "timeout": settings.llm_timeout},
            )
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                logger.warning(f"Gemini rate limited: {e}")
                raise RateLimitError(provider=self.name, retry_after=60)
            if "api key" in error_str or "403" in error_str:
                raise ProviderError(
                    message=f"Gemini auth error: {e}",
                    code="AUTH_ERROR",
                    details={"provider": self.name},
                )
            raise ProviderError(
                message=f"Gemini error: {e}",
                code="PROVIDER_ERROR",
                details={"provider": self.name},
            )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        """Stream Gemini response token by token."""
        self._ensure_client()
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            response = await asyncio.to_thread(
                self._model.generate_content,
                combined_prompt,
                generation_config=generation_config,
                stream=True,
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(provider=self.name, retry_after=60)
            raise ProviderError(
                message=f"Gemini stream error: {e}",
                code="STREAM_ERROR",
                details={"provider": self.name},
            )


# ============================================================
# Groq Llama 3.1 70B (Fallback — 30K TPM free tier)
# ============================================================

class GroqClient(BaseLLMProvider):
    """Groq-hosted Llama 3.1 70B client via groq SDK."""

    name = "groq"
    model = "llama-3.1-70b-versatile"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.groq_api_key
        self._client = None

    def _ensure_client(self) -> None:
        """Lazy-initialize the Groq client."""
        if self._client is None:
            try:
                from groq import Groq

                self._client = Groq(api_key=self.api_key)
                logger.info(f"Groq client initialized (model={self.model})")
            except Exception as e:
                raise ProviderError(
                    message=f"Failed to initialize Groq: {e}",
                    code="PROVIDER_INIT_ERROR",
                    details={"provider": self.name},
                )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Generate response via Groq API.

        Uses asyncio.to_thread since groq SDK is sync.
        """
        self._ensure_client()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=settings.llm_timeout,
            )

            text = response.choices[0].message.content
            if not text:
                raise ProviderError(
                    message="Groq returned empty response",
                    code="EMPTY_RESPONSE",
                    details={"provider": self.name},
                )

            logger.debug(f"Groq response: {len(text)} chars")
            return text

        except asyncio.TimeoutError:
            logger.warning(f"Groq timeout after {settings.llm_timeout}s")
            raise ProviderError(
                message=f"Groq timeout after {settings.llm_timeout}s",
                code="TIMEOUT",
                details={"provider": self.name, "timeout": settings.llm_timeout},
            )
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                logger.warning(f"Groq rate limited: {e}")
                raise RateLimitError(provider=self.name, retry_after=60)
            if "api key" in error_str or "authentication" in error_str:
                raise ProviderError(
                    message=f"Groq auth error: {e}",
                    code="AUTH_ERROR",
                    details={"provider": self.name},
                )
            raise ProviderError(
                message=f"Groq error: {e}",
                code="PROVIDER_ERROR",
                details={"provider": self.name},
            )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        """Stream Groq response token by token."""
        self._ensure_client()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(provider=self.name, retry_after=60)
            raise ProviderError(
                message=f"Groq stream error: {e}",
                code="STREAM_ERROR",
                details={"provider": self.name},
            )


# ============================================================
# Ollama (Local — optional, for offline / privacy mode)
# ============================================================

class OllamaClient(BaseLLMProvider):
    """Local Ollama client via HTTP API."""

    name = "ollama"
    model = "llama3.2:3b"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: Optional[str] = None,
    ):
        self.base_url = base_url
        if model:
            self.model = model
        self._http_client: Optional[httpx.AsyncClient] = None

    def _ensure_client(self) -> None:
        """Lazy-initialize the async HTTP client."""
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
        """Generate response via Ollama HTTP API."""
        self._ensure_client()

        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            response = await self._http_client.post("/api/generate", json=payload)
            response.raise_for_status()

            data = response.json()
            text = data.get("response", "")

            if not text:
                raise ProviderError(
                    message="Ollama returned empty response",
                    code="EMPTY_RESPONSE",
                    details={"provider": self.name},
                )

            logger.debug(f"Ollama response: {len(text)} chars")
            return text

        except httpx.ConnectError:
            raise ProviderError(
                message="Ollama is not running (connection refused)",
                code="PROVIDER_UNAVAILABLE",
                details={"provider": self.name, "url": self.base_url},
            )
        except httpx.TimeoutException:
            logger.warning(f"Ollama timeout after {settings.llm_timeout}s")
            raise ProviderError(
                message=f"Ollama timeout after {settings.llm_timeout}s",
                code="TIMEOUT",
                details={"provider": self.name},
            )
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                message=f"Ollama HTTP error: {e.response.status_code}",
                code="PROVIDER_ERROR",
                details={"provider": self.name, "status": e.response.status_code},
            )
        except Exception as e:
            raise ProviderError(
                message=f"Ollama error: {e}",
                code="PROVIDER_ERROR",
                details={"provider": self.name},
            )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream Ollama response token by token."""
        self._ensure_client()

        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with self._http_client.stream(
                "POST", "/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                import json

                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break

        except httpx.ConnectError:
            raise ProviderError(
                message="Ollama is not running",
                code="PROVIDER_UNAVAILABLE",
                details={"provider": self.name},
            )
        except Exception as e:
            raise ProviderError(
                message=f"Ollama stream error: {e}",
                code="STREAM_ERROR",
                details={"provider": self.name},
            )

    async def health_check(self) -> bool:
        """Check if Ollama is running and has the model available."""
        self._ensure_client()
        try:
            response = await self._http_client.get("/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                available = [m.get("name", "") for m in models]
                return any(self.model in name for name in available)
            return False
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
