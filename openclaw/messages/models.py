"""Core message types flowing through the gateway."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from openclaw.types import Channel, Intent


class Attachment(BaseModel):
    type: str  # "image", "video", "audio", "document"
    data: bytes | None = None
    url: str = ""
    mime_type: str = ""
    filename: str = ""


class InboundMessage(BaseModel):
    id: str
    channel: Channel
    user_id: str
    user_name: str = ""
    text: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    intent: Intent = Intent.UNKNOWN
    node_id: str = ""


class OutboundMessage(BaseModel):
    channel: Channel
    user_id: str
    text: str
    attachments: list[Attachment] = Field(default_factory=list)
    parse_mode: str = "markdown"
    metadata: dict = Field(default_factory=dict)
