"""Skill abstraction — a capability that handles a specific intent."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openclaw.config import OpenClawConfig
    from openclaw.connectors.base import ServiceConnector
    from openclaw.llm.router import LLMRouter
    from openclaw.observability.metrics import MetricsCollector

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.types import Intent


@dataclass
class SkillContext:
    """Injected dependencies available to every skill."""
    llm: LLMRouter
    connectors: dict[str, ServiceConnector]
    config: OpenClawConfig
    metrics: MetricsCollector


class Skill(abc.ABC):
    @abc.abstractmethod
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        """Process a message and produce a response."""

    @abc.abstractmethod
    def intents(self) -> list[Intent]:
        """Which intents this skill handles."""

    @abc.abstractmethod
    def name(self) -> str:
        """Skill identifier."""

    def description(self) -> str:
        return ""
