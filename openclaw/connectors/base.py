"""Service connector abstraction."""

from __future__ import annotations

import abc


class ServiceConnector(abc.ABC):
    @abc.abstractmethod
    async def health_check(self) -> dict:
        """Return health status."""

    @abc.abstractmethod
    def name(self) -> str:
        """Connector identifier."""

    async def connect(self) -> None:
        """Establish connection (optional override)."""

    async def disconnect(self) -> None:
        """Teardown (optional override)."""
