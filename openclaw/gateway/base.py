"""Channel adapter abstraction."""

from __future__ import annotations

import abc

from openclaw.messages.models import OutboundMessage


class ChannelAdapter(abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None:
        """Start listening for messages."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""

    @abc.abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        """Send a message back to the user."""

    @abc.abstractmethod
    def name(self) -> str:
        """Channel identifier."""
