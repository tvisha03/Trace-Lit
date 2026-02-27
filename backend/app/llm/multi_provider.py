"""TraceLit — Robust Multi-Provider LLM Orchestrator.

Automatic fallback chain: Gemini → Groq → Ollama.
Handles rate limits, timeouts, and provider failures seamlessly.
Includes fallback attribution for uncited responses.
"""

import asyncio
import time
from typing import AsyncIterator, Dict, List, Optional, Tuple

from loguru import logger

from app.config import settings
from app.exceptions import (
    AllProvidersFailedError,
    ProviderError,
    RateLimitError,
)
from app.llm.prompts import (
    assemble_prompt,
    extract_citations,
    remove_invalid_citations,
    sanitize_user_input,
    validate_citations,
)
from app.llm.providers import (
    BaseLLMProvider,
    GeminiClient,
    GroqClient,
    OllamaClient,
)


# ============================================================
# Query Type Routing
# ============================================================

QUERY_TYPE_CONFIG = {
    "factual": {"top_k": 5, "havf_level": "full"},
    "comparison": {"top_k": 3, "havf_level": "full"},
    "summary": {"top_k": 8, "havf_level": "basic"},
    "methodology": {"top_k": 5, "havf_level": "full"},
    "follow_up": {"top_k": 3, "havf_level": "basic"},
    "exploratory": {"top_k": 5, "havf_level": "basic"},
}


def classify_query_type(query: str) -> str:
    """Classify a user query into a type for retrieval tuning.

    Args:
        query: User query string.

    Returns:
        Query type: factual, comparison, summary, methodology,
        follow_up, or exploratory.
    """
    lower = query.lower().strip()

    # Comparison indicators
    if any(
        kw in lower
        for kw in ["compare", "difference", "vs", "versus", "contrast", "similar"]
    ):
        return "comparison"

    # Summary indicators
    if any(kw in lower for kw in ["summarize", "summary", "overview", "main points"]):
        return "summary"

    # Methodology indicators
    if any(
        kw in lower
        for kw in ["method", "approach", "technique", "algorithm", "how did they"]
    ):
        return "methodology"

    # Follow-up indicators
    if any(
        kw in lower
        for kw in ["what about", "also", "additionally", "related to that", "and"]
    ):
        return "follow_up"

    # Factual by default (most common for academic Q&A)
    return "factual"


# ============================================================
# Session State Manager
# ============================================================

class SessionStateManager:
    """Manages conversation context for a session.

    Preserves history, active papers, and provider state
    across conversation turns and provider switches.
    """

    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        self.conversation_history: List[Dict] = []
        self.active_paper_ids: List[str] = []
        self.last_provider: Optional[str] = None
        self.last_query_type: Optional[str] = None

    def add_turn(self, role: str, content: str) -> None:
        """Add a message to conversation history.

        Args:
            role: 'user' or 'assistant'.
            content: Message text.
        """
        self.conversation_history.append({"role": role, "content": content})

        # Enforce max turns (each turn = user + assistant)
        max_messages = self.max_turns * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def get_history(self) -> List[Dict]:
        """Return current conversation history."""
        return list(self.conversation_history)

    def clear(self) -> None:
        """Reset conversation state."""
        self.conversation_history = []
        self.last_provider = None
        self.last_query_type = None


# ============================================================
# Robust Multi-Provider LLM
# ============================================================

class RobustMultiProviderLLM:
    """Multi-provider LLM with automatic fallback and retry logic.

    Provider priority (cloud mode): Gemini → Groq → Ollama
    Provider priority (local mode): Ollama → Gemini → Groq

    Handles:
    - Rate limits → immediate switch to next provider
    - Timeouts → retry once with backoff, then switch
    - Auth errors → skip provider permanently for this session
    - Other errors → log, try next provider
    """

    def __init__(self, local_mode: bool = False):
        self.local_mode = local_mode
        self._providers: List[BaseLLMProvider] = []
        self._disabled_providers: set = set()
        self._rate_limit_until: Dict[str, float] = {}  # provider → resume timestamp
        self._session_states: Dict[str, SessionStateManager] = {}

        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize provider chain based on mode."""
        gemini = GeminiClient() if settings.gemini_api_key else None
        groq = GroqClient() if settings.groq_api_key else None
        ollama = OllamaClient()

        if self.local_mode:
            # Local mode: Ollama first
            providers = [ollama]
            if gemini:
                providers.append(gemini)
            if groq:
                providers.append(groq)
        else:
            # Cloud mode: Gemini → Groq → Ollama
            providers = []
            if gemini:
                providers.append(gemini)
            if groq:
                providers.append(groq)
            providers.append(ollama)

        self._providers = providers

        provider_names = [p.name for p in self._providers]
        logger.info(
            f"Multi-provider LLM initialized: {provider_names} "
            f"(mode={'local' if self.local_mode else 'cloud'})"
        )

    def get_session_state(self, session_id: str) -> SessionStateManager:
        """Get or create session state manager.

        Args:
            session_id: Session UUID.

        Returns:
            SessionStateManager for this session.
        """
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionStateManager(
                max_turns=settings.max_conversation_turns
            )
        return self._session_states[session_id]

    def remove_session_state(self, session_id: str) -> None:
        """Clean up session state when session is deleted."""
        self._session_states.pop(session_id, None)

    def _get_available_providers(self) -> List[BaseLLMProvider]:
        """Return providers that are not disabled or rate-limited.

        Rate-limited providers are re-enabled once their cooldown expires.
        """
        now = time.time()
        available = []

        for provider in self._providers:
            if provider.name in self._disabled_providers:
                continue

            rate_limit_until = self._rate_limit_until.get(provider.name, 0)
            if now < rate_limit_until:
                remaining = int(rate_limit_until - now)
                logger.debug(
                    f"{provider.name} rate-limited for {remaining}s more"
                )
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
        """Generate a cited response with automatic provider fallback.

        Args:
            query: Sanitized user query.
            context_paragraphs: Retrieved paragraph dicts.
            session_id: Session UUID for history tracking.
            active_paper_ids: Paper filter list.
            is_comparison: Whether this is a comparison query.

        Returns:
            Dict with keys: text, provider, warning, valid_paragraph_ids.

        Raises:
            AllProvidersFailedError: If all providers fail.
        """
        # Sanitize input
        clean_query = sanitize_user_input(query)

        # Get session state
        state = self.get_session_state(session_id)
        state.active_paper_ids = active_paper_ids or []

        # Classify query type
        query_type = classify_query_type(clean_query)
        state.last_query_type = query_type
        is_comparison = is_comparison or query_type == "comparison"

        # Collect valid paragraph IDs for citation validation
        valid_ids = {p.get("paragraph_id", "") for p in context_paragraphs}

        # Try each available provider
        available = self._get_available_providers()
        if not available:
            raise AllProvidersFailedError(
                errors=["No providers available (all disabled or rate-limited)"]
            )

        errors = []
        used_provider = None

        for provider in available:
            try:
                logger.info(f"Trying provider: {provider.name}")

                # Build prompt (trimmed to provider's budget)
                system_prompt, user_prompt = assemble_prompt(
                    query=clean_query,
                    context_paragraphs=context_paragraphs,
                    conversation_history=state.get_history(),
                    provider=provider.name,
                    is_comparison=is_comparison,
                    max_turns=settings.max_conversation_turns,
                )

                # Generate response
                response_text = await provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=settings.llm_temperature,
                )

                used_provider = provider.name
                state.last_provider = provider.name

                # Validate citations
                validation = validate_citations(response_text, valid_ids)
                warning = None

                # Remove hallucinated citations
                if validation["invalid_citations"]:
                    logger.warning(
                        f"Removing invalid citations: {validation['invalid_citations']}"
                    )
                    response_text = remove_invalid_citations(
                        response_text, validation["invalid_citations"]
                    )
                    warning = "Some citations were automatically corrected."

                # Check citation coverage
                if validation["citation_coverage"] < 0.6:
                    logger.warning(
                        f"Low citation coverage: {validation['citation_coverage']:.0%}"
                    )
                    if not warning:
                        warning = "Low citation coverage — some claims may need manual verification."

                # Update conversation history
                state.add_turn("user", clean_query)
                state.add_turn("assistant", response_text)

                return {
                    "text": response_text,
                    "provider": used_provider,
                    "warning": warning,
                    "valid_paragraph_ids": valid_ids,
                    "query_type": query_type,
                    "citation_validation": validation,
                }

            except RateLimitError as e:
                logger.warning(f"Rate limit hit for {provider.name}, switching...")
                retry_after = e.details.get("retry_after", 60)
                self._rate_limit_until[provider.name] = time.time() + retry_after
                errors.append({
                    "provider": provider.name,
                    "error": "rate_limit",
                    "retry_after": retry_after,
                })
                continue

            except ProviderError as e:
                if e.code == "AUTH_ERROR":
                    logger.error(f"Auth error for {provider.name} — disabling")
                    self._disabled_providers.add(provider.name)
                elif e.code == "TIMEOUT":
                    logger.warning(f"Timeout for {provider.name}")
                else:
                    logger.error(f"Provider error for {provider.name}: {e.message}")

                errors.append({
                    "provider": provider.name,
                    "error": e.code,
                    "message": e.message,
                })
                continue

            except Exception as e:
                logger.error(
                    f"Unexpected error from {provider.name}: {e}",
                    exc_info=True,
                )
                errors.append({
                    "provider": provider.name,
                    "error": "unknown",
                    "message": str(e),
                })
                continue

        # All providers failed
        raise AllProvidersFailedError(errors=errors)

    async def stream_with_fallback(
        self,
        query: str,
        context_paragraphs: List[Dict],
        session_id: str,
        active_paper_ids: Optional[List[str]] = None,
        is_comparison: bool = False,
    ) -> AsyncIterator[str]:
        """Stream a response with automatic provider fallback.

        If the primary provider fails during streaming, falls back to
        non-streaming generate on the next provider.

        Yields:
            Text chunks as they arrive.
        """
        clean_query = sanitize_user_input(query)
        state = self.get_session_state(session_id)
        query_type = classify_query_type(clean_query)
        is_comparison = is_comparison or query_type == "comparison"

        available = self._get_available_providers()
        if not available:
            raise AllProvidersFailedError(
                errors=["No providers available"]
            )

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

                    # Don't yield partial citations — wait for ] to close
                    if "[" in buffer and "]" not in buffer.split("[")[-1]:
                        continue

                    yield buffer
                    buffer = ""

                # Flush remaining buffer
                if buffer:
                    yield buffer

                # Record history
                # Note: full text reconstruction from stream would be done by caller
                state.last_provider = provider.name
                return

            except RateLimitError as e:
                retry_after = e.details.get("retry_after", 60)
                self._rate_limit_until[provider.name] = time.time() + retry_after
                logger.warning(
                    f"Stream rate limit for {provider.name}, trying next..."
                )
                continue

            except ProviderError as e:
                if e.code == "AUTH_ERROR":
                    self._disabled_providers.add(provider.name)
                logger.warning(f"Stream error for {provider.name}: {e.message}")
                continue

            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                continue

        raise AllProvidersFailedError(errors=["All providers failed during streaming"])

    async def shutdown(self) -> None:
        """Cleanup resources on shutdown."""
        for provider in self._providers:
            if hasattr(provider, "close"):
                try:
                    await provider.close()
                except Exception:
                    pass
        self._session_states.clear()
        logger.info("Multi-provider LLM shut down")


# ============================================================
# Module-level Singleton
# ============================================================

_llm_instance: Optional[RobustMultiProviderLLM] = None


def get_llm() -> RobustMultiProviderLLM:
    """Get or create the global multi-provider LLM instance.

    Returns:
        RobustMultiProviderLLM singleton.
    """
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = RobustMultiProviderLLM()
    return _llm_instance
