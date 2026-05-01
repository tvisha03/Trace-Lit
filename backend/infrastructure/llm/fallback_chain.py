
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

    def _is_temporarily_unavailable(
        self,
        provider: BaseLLMProvider,
    ) -> tuple[bool, float]:
        cooldown_seconds = self._rate_monitor.cooldown_remaining(provider.provider)
        return cooldown_seconds > 0.0, cooldown_seconds

    def _mark_provider_rate_limited(self, provider: BaseLLMProvider) -> float:
        return self._rate_monitor.mark_rate_limited(provider.provider)

    def _build_chain(self, use_local_llm: bool | None = None) -> List[BaseLLMProvider]:
        settings = get_settings()
        if use_local_llm is None:
            use_local_llm = settings.USE_LOCAL_LLM

        has_cloud = bool(settings.OLLAMA_API_KEY)

        if use_local_llm:
            # Ollama Cloud → Gemini → Groq → Local Ollama
            if has_cloud:
                order = [
                    LLMProvider.OLLAMA_CLOUD,
                    LLMProvider.GEMINI,
                    LLMProvider.GROQ,
                    LLMProvider.OLLAMA,
                ]
            else:
                order = [
                    LLMProvider.OLLAMA,
                    LLMProvider.GEMINI,
                    LLMProvider.GROQ,
                ]
        else:
            if has_cloud:
                order = [
                    LLMProvider.OLLAMA_CLOUD,
                    LLMProvider.GEMINI,
                    LLMProvider.GROQ,
                    LLMProvider.OLLAMA,
                ]
            else:
                order = [
                    LLMProvider.GEMINI,
                    LLMProvider.GROQ,
                    LLMProvider.OLLAMA,
                ]

        logger.info(f"Fallback chain: {' → '.join(p.value for p in order)}")
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
                cooldown_seconds = self._mark_provider_rate_limited(provider)
                logger.warning(
                    f"Rate limit on {provider.provider.value} — cooling down for "
                    f"{cooldown_seconds:.1f}s and switching"
                )
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
        estimated_tokens: int = 4_000,
    ) -> Tuple[str, LLMProvider, dict]:
        errors: List[str] = []
        deadline = time.monotonic() + self._request_timeout * 0.85

        for provider in self._providers:
            if time.monotonic() >= deadline:
                logger.warning("Aborting fallback chain: approaching request deadline")
                break

            is_cooling_down, cooldown_seconds = self._is_temporarily_unavailable(provider)
            if is_cooling_down:
                logger.info(
                    f"Skipping {provider.provider.value} — recent rate limit cooldown "
                    f"({cooldown_seconds:.1f}s remaining)"
                )
                errors.append(f"{provider.provider.value}: cooling_down")
                continue

            if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                # Wait for rate limit to clear instead of immediately skipping
                wait_secs = self._rate_monitor.seconds_until_available(
                    provider.provider, estimated_tokens
                )
                if wait_secs > 0 and (time.monotonic() + wait_secs) < deadline:
                    logger.info(
                        f"Waiting {wait_secs:.1f}s for {provider.provider.value} rate limit"
                    )
                    import asyncio
                    await asyncio.sleep(wait_secs)
                    # Re-check after waiting
                    if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                        logger.info(f"Skipping {provider.provider.value} — still over rate budget")
                        errors.append(f"{provider.provider.value}: rate_budget_exceeded")
                        continue
                else:
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
        streamed_any = False
        try:
            stream = provider.generate_streaming(
                system_prompt, user_prompt, temperature, max_tokens
            )
            async for token in stream:
                streamed_any = True
                full_text += token
                yield (token, provider.provider)

        except RateLimitError:
            cooldown_seconds = self._mark_provider_rate_limited(provider)
            logger.warning(
                f"Rate limit on {provider.provider.value} during stream — cooling down for "
                f"{cooldown_seconds:.1f}s and switching"
            )

        except (ProviderTimeoutError, EmptyResponseError) as exc:
            logger.warning(f"Stream error on {provider.provider.value}: {exc.message} — switching")

        except Exception as exc:
            logger.error(f"Stream unexpected on {provider.provider.value}: {exc}")

        finally:
            if streamed_any:
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
        estimated_tokens: int = 4_000,
    ) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
        errors: list[str] = []

        for provider in self._providers:
            is_cooling_down, cooldown_seconds = self._is_temporarily_unavailable(provider)
            if is_cooling_down:
                logger.info(
                    f"Skipping {provider.provider.value} stream — recent rate limit cooldown "
                    f"({cooldown_seconds:.1f}s remaining)"
                )
                errors.append(f"{provider.provider.value}: cooling_down")
                continue

            if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                # Wait for rate limit to clear instead of immediately skipping
                wait_secs = self._rate_monitor.seconds_until_available(
                    provider.provider, estimated_tokens
                )
                if wait_secs > 0:
                    logger.info(
                        f"Waiting {wait_secs:.1f}s for {provider.provider.value} stream rate limit"
                    )
                    import asyncio
                    await asyncio.sleep(wait_secs)
                    if not self._rate_monitor.can_make_request(provider.provider, estimated_tokens):
                        logger.info(f"Skipping {provider.provider.value} stream — still over rate budget")
                        errors.append(f"{provider.provider.value}: rate_budget_exceeded")
                        continue
                else:
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

    async def _should_retry_server_error(
        self,
        exc: Exception,
        attempt: int,
        max_retries: int,
        base_backoff: int,
        provider_name: str,
    ) -> bool:
        err_str = str(exc)
        is_server_error = any(code in err_str for code in ("500", "502", "503", "504"))
        if not is_server_error or attempt >= max_retries:
            return False
        wait = base_backoff * (2 ** attempt)
        logger.warning(
            f"{provider_name} server error (attempt {attempt + 1}) — retrying in {wait}s"
        )
        import asyncio
        await asyncio.sleep(wait)
        return True

    async def _try_vision_provider(
        self,
        provider: BaseLLMProvider,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        errors: list[str],
    ) -> str | None:
        """Attempt image analysis on one provider with server-error retries.

        Returns the raw text on success, or None if the provider must be skipped.
        Appends a reason string to *errors* on every failure.
        """
        _SERVER_RETRIES = 2
        _SERVER_BACKOFF_BASE = 3

        for attempt in range(1 + _SERVER_RETRIES):
            try:
                result = await provider.analyze_image(
                    image_data, mime_type, prompt, temperature, max_tokens,
                )
                return result

            except NotImplementedError:
                errors.append(f"{provider.provider.value}: no_vision_support")
                return None  # vision not supported — skip this provider

            except RateLimitError:
                cooldown_seconds = self._mark_provider_rate_limited(provider)
                logger.warning(
                    f"Rate limit on {provider.provider.value} vision — cooling down for "
                    f"{cooldown_seconds:.1f}s and switching"
                )
                errors.append(f"{provider.provider.value}: rate_limited")
                return None  # rate-limited — skip this provider

            except Exception as exc:
                if await self._should_retry_server_error(
                    exc, attempt, _SERVER_RETRIES, _SERVER_BACKOFF_BASE,
                    provider.provider.value,
                ):
                    continue
                errors.append(f"{provider.provider.value}: {exc}")
                return None

        return None  # exhausted retries

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> tuple[str, LLMProvider]:
        """Analyze an image with the first vision-capable provider.

        Vision pipeline: Ollama Cloud → Gemini → Local Ollama.
        Groq is skipped automatically (raises NotImplementedError).
        """
        errors: list[str] = []

        for provider in self._providers:
            is_cooling_down, cooldown_seconds = self._is_temporarily_unavailable(provider)
            if is_cooling_down:
                errors.append(f"{provider.provider.value}: cooling_down")
                logger.info(
                    f"Skipping {provider.provider.value} vision — recent rate limit cooldown "
                    f"({cooldown_seconds:.1f}s remaining)"
                )
                continue

            result = await self._try_vision_provider(
                provider, image_data, mime_type, prompt, temperature, max_tokens, errors,
            )
            if result is not None:
                logger.info(f"Image analysis from {provider.provider.value}")
                return result, provider.provider

        logger.error(f"All providers failed for image analysis: {errors}")
        raise AllProvidersFailedError()

