"""TraceLit — Robust Multi-Provider LLM Fallback Chain.

Automatic fallback: Gemini → Groq → Ollama.
Handles rate limits, timeouts, and provider failures seamlessly.
"""

import time
from typing import AsyncIterator, Dict, List, Optional

from loguru import logger

from app.config import settings
from domain.generation.prompts import assemble_prompt, sanitize_user_input, validate_citations, remove_invalid_citations
from infrastructure.llm.base import BaseLLMProvider
from infrastructure.llm.factory import build_provider_chain
from infrastructure.llm.session_state import SessionStateManager
from shared.errors import AllProvidersFailedError, ProviderError, RateLimitError


# ============================================================
# Robust Multi-Provider LLM
# ============================================================

class RobustMultiProviderLLM:
    """Multi-provider LLM with automatic fallback and retry logic."""

    # AUTH_ERRORs needed in a row before a provider is permanently disabled.
    # Free-tier keys can get transient 401/403 from safety blocks without being
    # truly invalid, so we require 3 consecutive failures before giving up.
    _AUTH_FAILURE_LIMIT = 3

    def __init__(self, local_mode: bool = False):
        self.local_mode = local_mode
        self._providers: List[BaseLLMProvider] = build_provider_chain(local_mode)
        self._disabled_providers: set = set()
        self._rate_limit_until: Dict[str, float] = {}
        self._session_states: Dict[str, SessionStateManager] = {}
        # Consecutive AUTH_ERROR count per provider — reset on success
        self._auth_failures: Dict[str, int] = {}

        provider_names = [p.name for p in self._providers]
        logger.info(f"Multi-provider LLM: {provider_names} ({'local' if local_mode else 'cloud'} mode)")

    def get_session_state(self, session_id: str) -> SessionStateManager:
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionStateManager(max_turns=settings.max_conversation_turns)
        return self._session_states[session_id]

    def remove_session_state(self, session_id: str) -> None:
        self._session_states.pop(session_id, None)

    def _get_available_providers(self) -> List[BaseLLMProvider]:
        now = time.time()
        available = []
        for provider in self._providers:
            if provider.name in self._disabled_providers:
                continue
            if now < self._rate_limit_until.get(provider.name, 0):
                continue
            available.append(provider)
        return available

    async def generate(
        self,
        query: str,
        context_paragraphs: List[Dict],
        session_id: str,
        active_paper_ids: Optional[List[str]] = None,
        is_comparison: bool = False,
    ) -> Dict:
        """Generate a cited response with automatic provider fallback."""
        from domain.generation.chat_engine import classify_query_type

        clean_query = sanitize_user_input(query)
        state = self.get_session_state(session_id)
        state.active_paper_ids = active_paper_ids or []

        query_type = classify_query_type(clean_query)
        state.last_query_type = query_type
        is_comparison = is_comparison or query_type == "comparison"
        valid_ids = {p.get("paragraph_id", "") for p in context_paragraphs}

        available = self._get_available_providers()
        if not available:
            raise AllProvidersFailedError(errors=["No providers available"])

        errors = []

        for provider in available:
            try:
                logger.info(f"Trying provider: {provider.name}")

                system_prompt, user_prompt = assemble_prompt(
                    query=clean_query,
                    context_paragraphs=context_paragraphs,
                    conversation_history=state.get_history(),
                    provider=provider.name,
                    is_comparison=is_comparison,
                    max_turns=settings.max_conversation_turns,
                )

                response_text = await provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=settings.llm_temperature,
                )

                state.last_provider = provider.name

                validation = validate_citations(response_text, valid_ids)
                warning = None

                if validation["invalid_citations"]:
                    response_text = remove_invalid_citations(response_text, validation["invalid_citations"])
                    warning = "Some citations were automatically corrected."

                if validation["citation_coverage"] < 0.6 and not warning:
                    warning = "Low citation coverage — some claims may need manual verification."

                state.add_turn("user", clean_query)
                state.add_turn("assistant", response_text)

                # Reset any previous auth-failure count on success
                self._auth_failures.pop(provider.name, None)

                return {
                    "text": response_text,
                    "provider": provider.name,
                    "warning": warning,
                    "valid_paragraph_ids": valid_ids,
                    "query_type": query_type,
                    "citation_validation": validation,
                }

            except RateLimitError as e:
                retry_after = e.details.get("retry_after", 60)
                self._rate_limit_until[provider.name] = time.time() + retry_after
                logger.warning(f"{provider.name} rate-limited, backing off {retry_after}s")
                errors.append({"provider": provider.name, "error": "rate_limit"})
                continue

            except ProviderError as e:
                if e.code == "AUTH_ERROR":
                    count = self._auth_failures.get(provider.name, 0) + 1
                    self._auth_failures[provider.name] = count
                    if count >= self._AUTH_FAILURE_LIMIT:
                        self._disabled_providers.add(provider.name)
                        logger.error(
                            f"{provider.name} permanently disabled after "
                            f"{count} consecutive AUTH_ERRORs"
                        )
                    else:
                        logger.warning(
                            f"{provider.name} AUTH_ERROR #{count}/{self._AUTH_FAILURE_LIMIT} "
                            f"(not yet disabled): {e.message}"
                        )
                errors.append({"provider": provider.name, "error": e.code, "message": e.message})
                continue

            except Exception as e:
                logger.error(f"Unexpected error from {provider.name}: {e}", exc_info=True)
                errors.append({"provider": provider.name, "error": "unknown", "message": str(e)})
                continue

        raise AllProvidersFailedError(errors=errors)

    async def stream_with_fallback(
        self,
        query: str,
        context_paragraphs: List[Dict],
        session_id: str,
        active_paper_ids: Optional[List[str]] = None,
        is_comparison: bool = False,
    ) -> AsyncIterator[str]:
        """Stream a response with automatic provider fallback."""
        from domain.generation.chat_engine import classify_query_type

        clean_query = sanitize_user_input(query)
        state = self.get_session_state(session_id)
        query_type = classify_query_type(clean_query)
        is_comparison = is_comparison or query_type == "comparison"

        available = self._get_available_providers()
        if not available:
            raise AllProvidersFailedError(errors=["No providers available"])

        for provider in available:
            try:
                system_prompt, user_prompt = assemble_prompt(
                    query=clean_query,
                    context_paragraphs=context_paragraphs,
                    conversation_history=state.get_history(),
                    provider=provider.name,
                    is_comparison=is_comparison,
                )

                buffer = ""
                async for chunk in provider.stream(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=settings.llm_temperature,
                ):
                    buffer += chunk
                    if "[" in buffer and "]" not in buffer.split("[")[-1]:
                        continue
                    yield buffer
                    buffer = ""

                if buffer:
                    yield buffer

                state.last_provider = provider.name
                # Reset any previous auth-failure count on success
                self._auth_failures.pop(provider.name, None)
                return

            except RateLimitError as e:
                retry_after = e.details.get("retry_after", 60)
                logger.warning(f"Provider {provider.name} rate-limited, backing off {retry_after}s")
                self._rate_limit_until[provider.name] = time.time() + retry_after
                continue

            except ProviderError as e:
                logger.warning(f"Provider {provider.name} failed ({e.code}): {e.message}")
                if e.code == "AUTH_ERROR":
                    count = self._auth_failures.get(provider.name, 0) + 1
                    self._auth_failures[provider.name] = count
                    if count >= self._AUTH_FAILURE_LIMIT:
                        self._disabled_providers.add(provider.name)
                        logger.error(
                            f"{provider.name} permanently disabled after "
                            f"{count} consecutive AUTH_ERRORs"
                        )
                    else:
                        logger.warning(
                            f"{provider.name} AUTH_ERROR #{count}/{self._AUTH_FAILURE_LIMIT} "
                            f"(not yet disabled): {e.message}"
                        )
                continue

            except Exception as e:
                logger.error(f"Unexpected stream error from {provider.name}: {e}", exc_info=True)
                continue

        raise AllProvidersFailedError(errors=["All providers failed during streaming"])

    async def shutdown(self) -> None:
        for provider in self._providers:
            if hasattr(provider, "close"):
                try:
                    await provider.close()
                except Exception:
                    pass
        self._session_states.clear()
        logger.info("Multi-provider LLM shut down")


# Module-level singleton
_llm_instance: Optional[RobustMultiProviderLLM] = None


def get_llm() -> RobustMultiProviderLLM:
    """Get or create the global multi-provider LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = RobustMultiProviderLLM()
    return _llm_instance
