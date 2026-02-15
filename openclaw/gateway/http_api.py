"""HTTP REST API adapter — programmatic access to OpenClaw."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from openclaw.messages.models import InboundMessage
from openclaw.types import Channel

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/v1", tags=["api"])


class MessageRequest(BaseModel):
    text: str
    user_id: str = "api-user"
    node_id: str = ""


class MessageResponse(BaseModel):
    text: str
    intent: str
    model: str = ""
    latency_ms: int = 0


# The dispatch function is injected at app startup
_dispatch_fn = None


def set_dispatch(fn):
    global _dispatch_fn
    _dispatch_fn = fn


@router.post("/message", response_model=MessageResponse)
async def send_message(req: MessageRequest):
    if not _dispatch_fn:
        raise HTTPException(503, "Gateway not initialized")

    msg = InboundMessage(
        id=str(uuid.uuid4()),
        channel=Channel.HTTP_API,
        user_id=req.user_id,
        text=req.text,
        node_id=req.node_id,
    )
    result = await _dispatch_fn(msg)
    return MessageResponse(text=result.text, intent=msg.intent.value)


@router.post("/diagnose", response_model=MessageResponse)
async def diagnose(req: MessageRequest):
    if not _dispatch_fn:
        raise HTTPException(503, "Gateway not initialized")

    msg = InboundMessage(
        id=str(uuid.uuid4()),
        channel=Channel.HTTP_API,
        user_id=req.user_id,
        text=req.text or "Why is this equipment stopped?",
        node_id=req.node_id,
    )
    # Force diagnose intent
    from openclaw.types import Intent
    msg.intent = Intent.DIAGNOSE
    result = await _dispatch_fn(msg)
    return MessageResponse(text=result.text, intent="diagnose")
