"""
Multi-provider fallback chain: Gemini → Groq → Ollama.

Handles rate limits, timeouts, and empty responses transparently.
The caller never needs to know which provider actually answered.
"""

from typing import AsyncGenerator

from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.factory import create_provider
from shared.enums import LLMProvider
from shared.errors import (
    RateLimitError,
    ProviderTimeoutError,
    EmptyResponseError,
    AllProvidersFailedError,
)
from shared.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)


class FallbackChain:
    """
    Tries providers in priority order.
    On 429 → switch immediately (no retry).
    On timeout → retry per provider up to LLM_MAX_RETRIES, then switch.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._max_retries = settings.LLM_MAX_RETRIES
        self._retry_delay = settings.LLM_RETRY_DELAY_BASE
        self._providers = self._build_chain()

    def _build_chain(self) -> list[BaseLLMProvider]:
        """Build provider list respecting USE_LOCAL_LLM toggle."""
        settings = get_settings()
        if settings.USE_LOCAL_LLM:
            # Local-first: Ollama → Gemini → Groq
            order = [LLMProvider.OLLAMA, LLMProvider.GEMINI, LLMProvider.GROQ]
        else:
            # Cloud-first: Gemini → Groq → Ollama
            order = [LLMProvider.GEMINI, LLMProvider.GROQ, LLMProvider.OLLAMA]
        return [create_provider(p) for p in order]

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> tuple[str, LLMProvider, dict]:
        """
        Try each provider until one succeeds.

        Returns
        -------
        tuple of (response_text, provider_used, metadata_dict)
        """
        errors: list[str] = []

        for provider in self._providers:
            retries = 0
            while retries <= self._max_retries:
                try:
                    text = await provider.generate(
                        system_prompt, user_prompt, temperature, max_tokens
                    )
                    logger.info(f"LLM response from {provider.provider.value}")
                    return text, provider.provider, {"retries": retries}

                except RateLimitError:
                    # Switch immediately — retrying the same provider wastes time
                    logger.warning(f"Rate limit on {provider.provider.value} — switching")
                    errors.append(f"{provider.provider.value}: rate_limit")
                    break

                except (ProviderTimeoutError, EmptyResponseError) as exc:
                    retries += 1
                    logger.warning(
                        f"{provider.provider.value} attempt {retries}: {exc.message}"
                    )
                    errors.append(f"{provider.provider.value}: {exc.message}")
                    if retries > self._max_retries:
                        break
                    import asyncio
                    await asyncio.sleep(self._retry_delay * retries)

                except Exception as exc:
                    logger.error(f"{provider.provider.value} unexpected: {exc}")
                    errors.append(f"{provider.provider.value}: {exc}")
                    break

        logger.error(f"All providers failed: {errors}")
        raise AllProvidersFailedError()

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[tuple[str, LLMProvider], None]:
        """
        Stream tokens from the first available provider.
        Yields (token_chunk, provider) tuples.
        """
        for provider in self._providers:
            try:
                async for token in provider.generate_streaming(
                    system_prompt, user_prompt, temperature, max_tokens
                ):
                    yield token, provider.provider
                return  # stream completed successfully

            except RateLimitError:
                logger.warning(f"Rate limit on {provider.provider.value} during stream — switching")
                continue

            except (ProviderTimeoutError, EmptyResponseError) as exc:
                logger.warning(f"Stream error on {provider.provider.value}: {exc.message} — switching")
                continue

            except Exception as exc:
                logger.error(f"Stream unexpected on {provider.provider.value}: {exc}")
                continue

        raise AllProvidersFailedError()
