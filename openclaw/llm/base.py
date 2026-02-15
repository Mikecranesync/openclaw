"""LLM provider abstraction."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    tokens_used: int = 0
    latency_ms: int = 0
    raw: dict | None = field(default=None, repr=False)


class LLMProvider(abc.ABC):
    """Base class for all LLM provider integrations."""

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a chat completion request."""

    @abc.abstractmethod
    async def complete_with_vision(
        self,
        messages: list[dict],
        images: list[bytes],
        system_prompt: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send a vision request with images."""

    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True if credentials are configured."""

    def supports_vision(self) -> bool:
        """True if provider handles image inputs."""
        return False
