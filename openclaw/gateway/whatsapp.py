"""WhatsApp adapter — bridges through Clawdbot gateway."""

from __future__ import annotations

import logging

import httpx

from openclaw.gateway.base import ChannelAdapter
from openclaw.messages.models import OutboundMessage

logger = logging.getLogger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """Connects to Clawdbot gateway for WhatsApp messaging."""

    def __init__(self, gateway_url: str = "http://localhost:18789") -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._gateway_url, timeout=15.0)
        logger.info("WhatsApp adapter connected to Clawdbot at %s", self._gateway_url)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def send(self, message: OutboundMessage) -> None:
        if not self._client:
            return
        await self._client.post(
            "/send",
            json={"to": message.user_id, "text": message.text},
        )

    def name(self) -> str:
        return "whatsapp"
