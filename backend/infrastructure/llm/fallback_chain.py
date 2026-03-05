
from __future__ import annotations

import time
from typing import AsyncGenerator, Tuple, Optional, List

from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.factory import create_provider
from infrastructure.llm.rate_monitor import RateLimitMonitor
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

    def __init__(self) -> None:
        settings = get_settings()
        self._max_retries = settings.LLM_MAX_RETRIES
        self._retry_delay = settings.LLM_RETRY_DELAY_BASE
        self._request_timeout = settings.REQUEST_TIMEOUT
        self._providers = self._build_chain()
        self._rate_monitor = RateLimitMonitor()

    @property
    def rate_monitor(self) -> RateLimitMonitor:
        return self._rate_monitor

    def _build_chain(self, use_local_llm: bool | None = None) -> List[BaseLLMProvider]:
        if use_local_llm is None:
            use_local_llm = get_settings().USE_LOCAL_LLM
        if use_local_llm:
            order = [LLMProvider.OLLAMA, LLMProvider.GEMINI, LLMProvider.GROQ]
        else:
            order = [LLMProvider.GEMINI, LLMProvider.GROQ, LLMProvider.OLLAMA]
        return [create_provider(p) for p in order]

    @property
    def providers(self) -> List[BaseLLMProvider]:
        return self._providers

    async def _try_provider(
        self,
        provider: BaseLLMProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        deadline: float,
    ) -> Optional[Tuple[str, int]]:
        retries = 0
        while retries <= self._max_retries:
            if time.monotonic() >= deadline:
                logger.warning(
                    f"Aborting {provider.provider.value}: approaching request deadline"
                )
                return None

            try:
                text = await provider.generate(
                    system_prompt, user_prompt, temperature, max_tokens
                )
                return text, retries

            except RateLimitError:
                logger.warning(f"Rate limit on {provider.provider.value} — switching")
                return None

            except (ProviderTimeoutError, EmptyResponseError) as exc:
                retries += 1
                logger.warning(f"{provider.provider.value} attempt {retries}: {exc.message}")
                if retries > self._max_retries:
                    return None
                import asyncio
                await asyncio.sleep(self._retry_delay * retries)

            except Exception as exc:
                logger.error(f"{provider.provider.value} unexpected: {exc}")
                return None
        return None

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        estimated_tokens: int = 8_500,
    ) -> Tuple[str, LLMProvider, dict]:
        errors: List[str] = []
        deadline = time.monotonic() + self._request_timeout * 0.85

        for provider in self._providers:
            if time.monotonic() >= deadline:
                logger.warning("Aborting fallback chain: approaching request deadline")
                break

            if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                logger.info(f"Skipping {provider.provider.value} — over rate budget")
                errors.append(f"{provider.provider.value}: rate_budget_exceeded")
                continue

            result = await self._try_provider(
                provider, system_prompt, user_prompt, temperature, max_tokens,
                deadline,
            )
            if result is None:
                errors.append(f"{provider.provider.value}: failed")
                continue

            text, retries = result
            from shared.utils.text_utils import estimate_tokens as _est
            self._rate_monitor.track_usage(
                provider.provider, _est(system_prompt + user_prompt + text),
            )
            logger.info(f"LLM response from {provider.provider.value}")
            return text, provider.provider, {"retries": retries}

        logger.error(f"All providers failed: {errors}")
        raise AllProvidersFailedError()

    async def _stream_from_provider(
        self,
        provider: BaseLLMProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
        full_text = ""
        try:
            stream = provider.generate_streaming(
                system_prompt, user_prompt, temperature, max_tokens
            )
            async for token in stream:
                full_text += token
                yield (token, provider.provider)

        except RateLimitError:
            logger.warning(f"Rate limit on {provider.provider.value} during stream — switching")

        except (ProviderTimeoutError, EmptyResponseError) as exc:
            logger.warning(f"Stream error on {provider.provider.value}: {exc.message} — switching")

        except Exception as exc:
            logger.error(f"Stream unexpected on {provider.provider.value}: {exc}")

        finally:
            from shared.utils.text_utils import estimate_tokens as _est
            input_tokens = _est(system_prompt + user_prompt)
            output_tokens = _est(full_text) if full_text else 0
            self._rate_monitor.track_usage(
                provider.provider, input_tokens + output_tokens,
            )

    async def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        estimated_tokens: int = 8_500,
    ) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
        errors: list[str] = []

        for provider in self._providers:
            if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                logger.info(f"Skipping {provider.provider.value} stream — over rate budget")
                errors.append(f"{provider.provider.value}: rate_budget_exceeded")
                continue

            yielded_at_least_one = False
            async for item in self._stream_from_provider(
                provider, system_prompt, user_prompt, temperature, max_tokens
            ):
                yielded_at_least_one = True
                yield item

            if yielded_at_least_one:
                return

            logger.warning(
                f"{provider.provider.value} stream yielded no tokens — trying next provider"
            )
            errors.append(f"{provider.provider.value}: stream_yielded_nothing")

        logger.error(f"All providers failed for streaming: {errors}")
        raise AllProvidersFailedError()

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> tuple[str, LLMProvider]:
        errors: list[str] = []

        for provider in self._providers:
            try:
                result = await provider.analyze_image(
                    image_data, mime_type, prompt, temperature, max_tokens,
                )
                logger.info(f"Image analysis from {provider.provider.value}")
                return result, provider.provider

            except NotImplementedError:
                errors.append(f"{provider.provider.value}: no_vision_support")
                continue

            except RateLimitError:
                errors.append(f"{provider.provider.value}: rate_limited")
                continue

            except Exception as exc:
                errors.append(f"{provider.provider.value}: {exc}")
                continue

        logger.error(f"All providers failed for image analysis: {errors}")
        raise AllProvidersFailedError()

