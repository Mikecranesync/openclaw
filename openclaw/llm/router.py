"""LLM Router — selects provider by intent with fallback chain."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from openclaw.llm.base import LLMProvider, LLMResponse
from openclaw.llm.budget import BudgetTracker
from openclaw.types import Intent

logger = logging.getLogger(__name__)


@dataclass
class Route:
    primary: str
    fallbacks: list[str] = field(default_factory=list)


# Default routing table
DEFAULT_ROUTES: dict[Intent, Route] = {
    Intent.DIAGNOSE: Route("openrouter", ["groq", "nvidia", "openai"]),
    Intent.STATUS: Route("groq", ["openai"]),
    Intent.PHOTO: Route("gemini", ["openai", "openrouter"]),
    Intent.WORK_ORDER: Route("openrouter", ["anthropic", "openai", "groq"]),
    Intent.CHAT: Route("groq", ["openrouter", "openai"]),
    Intent.SEARCH: Route("groq", []),
    Intent.ADMIN: Route("groq", []),
    Intent.HELP: Route("groq", []),
    Intent.UNKNOWN: Route("groq", ["openrouter", "openai"]),
}


class LLMRouter:
    """Selects the right LLM provider based on intent, budget, and availability."""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        budget: BudgetTracker | None = None,
        routes: dict[Intent, Route] | None = None,
    ) -> None:
        self.providers = providers
        self.budget = budget or BudgetTracker()
        self.routes = routes or DEFAULT_ROUTES

    async def route(
        self,
        intent: Intent,
        messages: list[dict],
        system_prompt: str = "",
        images: list[bytes] | None = None,
        prefer: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Select provider and execute request with automatic fallback."""
        # If explicit provider requested
        if prefer and prefer in self.providers:
            provider = self.providers[prefer]
            if provider.is_available() and self.budget.is_within_budget(prefer):
                return await self._call(provider, messages, system_prompt, images, max_tokens, temperature)

        # Get route for this intent
        route = self.routes.get(intent, Route("groq", ["openai"]))
        candidates = [route.primary] + route.fallbacks

        attempted = []
        for provider_name in candidates:
            provider = self.providers.get(provider_name)
            if not provider or not provider.is_available():
                continue
            if not self.budget.is_within_budget(provider_name):
                logger.warning("Provider %s over budget, skipping", provider_name)
                continue
            if images and not provider.supports_vision():
                continue

            attempted.append(provider_name)
            try:
                response = await self._call(provider, messages, system_prompt, images, max_tokens, temperature)
                self.budget.record(provider_name, response.tokens_used)
                return response
            except Exception:
                logger.exception("Provider %s failed, trying fallback", provider_name)
                continue

        raise RuntimeError(
            f"All LLM providers exhausted for intent={intent.value}, "
            f"tried: {attempted or candidates}"
        )

    async def _call(
        self,
        provider: LLMProvider,
        messages: list[dict],
        system_prompt: str,
        images: list[bytes] | None,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        start = time.monotonic()
        if images:
            response = await provider.complete_with_vision(
                messages, images, system_prompt=system_prompt, max_tokens=max_tokens
            )
        else:
            response = await provider.complete(
                messages, system_prompt=system_prompt, max_tokens=max_tokens, temperature=temperature
            )
        response.latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "LLM response: provider=%s model=%s tokens=%d latency=%dms",
            response.provider, response.model, response.tokens_used, response.latency_ms,
        )
        return response
