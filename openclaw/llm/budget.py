"""Token and request budget tracking per LLM provider."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class ProviderBudget:
    daily_request_limit: int = 0  # 0 = unlimited
    daily_token_limit: int = 0
    requests_today: int = 0
    tokens_today: int = 0
    last_reset: date = field(default_factory=date.today)

    def _maybe_reset(self) -> None:
        today = date.today()
        if today > self.last_reset:
            self.requests_today = 0
            self.tokens_today = 0
            self.last_reset = today

    def is_within_budget(self) -> bool:
        self._maybe_reset()
        if self.daily_request_limit and self.requests_today >= self.daily_request_limit:
            return False
        if self.daily_token_limit and self.tokens_today >= self.daily_token_limit:
            return False
        return True

    def record(self, tokens: int = 0) -> None:
        self._maybe_reset()
        self.requests_today += 1
        self.tokens_today += tokens
        if self.daily_request_limit:
            pct = (self.requests_today / self.daily_request_limit) * 100
            if pct >= 90:
                logger.warning("Budget warning: %d%% of daily request limit used", int(pct))


class BudgetTracker:
    """Tracks budgets across all providers."""

    def __init__(self) -> None:
        self._budgets: dict[str, ProviderBudget] = {}

    def configure(self, provider: str, daily_request_limit: int = 0, daily_token_limit: int = 0) -> None:
        self._budgets[provider] = ProviderBudget(
            daily_request_limit=daily_request_limit,
            daily_token_limit=daily_token_limit,
        )

    def is_within_budget(self, provider: str) -> bool:
        budget = self._budgets.get(provider)
        if not budget:
            return True
        return budget.is_within_budget()

    def record(self, provider: str, tokens: int = 0) -> None:
        budget = self._budgets.get(provider)
        if budget:
            budget.record(tokens)

    def summary(self) -> dict[str, dict]:
        return {
            name: {
                "requests_today": b.requests_today,
                "tokens_today": b.tokens_today,
                "daily_request_limit": b.daily_request_limit,
                "within_budget": b.is_within_budget(),
            }
            for name, b in self._budgets.items()
        }
