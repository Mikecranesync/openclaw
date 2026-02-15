"""WebSocket adapter placeholder."""

from __future__ import annotations

from openclaw.gateway.base import ChannelAdapter
from openclaw.messages.models import OutboundMessage


class WebSocketAdapter(ChannelAdapter):
    """WebSocket support — implemented via FastAPI WebSocket routes in app.py."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, message: OutboundMessage) -> None:
        pass  # Handled by FastAPI WebSocket endpoint

    def name(self) -> str:
        return "websocket"
