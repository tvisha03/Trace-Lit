"""TraceLit — Google Gemini 2.0 Flash provider (google-genai SDK).

Free-tier safe:
  - system_instruction passed via GenerateContentConfig (not concatenated)
  - INVALID_ARGUMENT treated as soft error, not AUTH_ERROR
  - Safety / recitation blocks (empty response) treated as retryable PROVIDER_ERROR
  - AUTH_ERROR only raised for confirmed invalid-key strings
"""

import asyncio
from typing import AsyncIterator, Optional

from loguru import logger

from app.config import settings
from infrastructure.llm.base import BaseLLMProvider
from shared.errors import ProviderError, RateLimitError

# Strings that confirm the API key itself is rejected (not just a bad request)
_AUTH_ERROR_SIGNALS = (
    "api key not valid",
    "api_key_invalid",
    "invalid api key",
    "api key is invalid",
    "permission_denied",
    "credentials",
    "unauthenticated",
    "401",
)


class GeminiClient(BaseLLMProvider):
    """Google Gemini 2.0 Flash via the google-genai SDK."""

    name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = settings.gemini_model
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is None:
            try:
                from google import genai  # google-genai >= 1.0
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini client initialised (model={self.model})")
            except Exception as e:
                raise ProviderError(
                    message=f"Failed to initialise Gemini: {e}",
                    code="PROVIDER_INIT_ERROR",
                    details={"provider": self.name},
                )

    def _make_config(self, system_prompt: str, temperature: float, max_tokens: int):
        """Build GenerateContentConfig with system_instruction set separately.

        Passing system_instruction via config (not concatenated into the user
        prompt) avoids INVALID_ARGUMENT errors on the free tier and gives
        Gemini the two-turn structure it expects.

        Gemini 2.5 Flash is a thinking model: internal reasoning tokens count
        against max_output_tokens, so enforce a practical minimum of 1024 to
        avoid MAX_TOKENS before any response text is produced.
        """
        from google.genai import types
        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max(max_tokens, 1024),
        )

    def _classify_error(self, e: Exception):
        """Map an exception to the correct domain error.

        Rules:
          - 429 / quota / resource_exhausted → RateLimitError  (retryable)
          - confirmed bad-key strings         → AUTH_ERROR      (permanent)
          - everything else                   → PROVIDER_ERROR  (retryable)
        """
        err = str(e).lower()
        if "429" in err or "rate" in err or "quota" in err or "resource_exhausted" in err:
            logger.warning(f"Gemini rate limited: {e}")
            return RateLimitError(provider=self.name, retry_after=60)
        if any(sig in err for sig in _AUTH_ERROR_SIGNALS):
            logger.error(f"Gemini API key rejected: {e}")
            return ProviderError(
                message=f"Gemini auth error: {e}",
                code="AUTH_ERROR",
                details={"provider": self.name},
            )
        # INVALID_ARGUMENT, SAFETY, RECITATION, UNAVAILABLE, 403 (not key) → soft
        logger.warning(f"Gemini transient error ({type(e).__name__}): {e}")
        return ProviderError(
            message=f"Gemini error: {e}",
            code="PROVIDER_ERROR",
            details={"provider": self.name},
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        self._ensure_client()
        # system_instruction goes into config; user_prompt is the sole content
        config = self._make_config(system_prompt, temperature, max_tokens)
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                ),
                timeout=settings.llm_timeout,
            )

            # Gemini can return a valid object with no text when the safety
            # filter or recitation detector fires — treat as soft error.
            if not response or not response.text:
                finish = None
                try:
                    finish = response.candidates[0].finish_reason.name
                except Exception:
                    pass
                reason = finish or "empty"
                logger.warning(f"Gemini returned no text (finish_reason={reason})")
                raise ProviderError(
                    message=f"Gemini empty response (finish_reason={reason})",
                    code="PROVIDER_ERROR",   # retryable — NOT AUTH_ERROR
                    details={"provider": self.name, "finish_reason": reason},
                )

            logger.debug(f"Gemini response: {len(response.text)} chars")
            return response.text

        except asyncio.TimeoutError:
            logger.warning(f"Gemini timeout after {settings.llm_timeout}s")
            raise ProviderError(
                message=f"Gemini timeout after {settings.llm_timeout}s",
                code="TIMEOUT",
                details={"provider": self.name},
            )
        except (ProviderError, RateLimitError):
            raise
        except Exception as e:
            raise self._classify_error(e)

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        self._ensure_client()
        # system_instruction goes into config; user_prompt is the sole content
        config = self._make_config(system_prompt, temperature, max_tokens)
        try:
            # generate_content_stream returns an AsyncIterator — do NOT await it
            async for chunk in self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=user_prompt,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except (ProviderError, RateLimitError):
            raise
        except Exception as e:
            raise self._classify_error(e)
