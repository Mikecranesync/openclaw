"""ChatSkill — general conversation with factory context."""

from __future__ import annotations

from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent


class ChatSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        response = await context.llm.route(
            Intent.CHAT,
            messages=[{"role": "user", "content": message.text}],
            system_prompt=SYSTEM_PROMPT,
        )
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text,
        )

    def intents(self) -> list[Intent]:
        return [Intent.CHAT, Intent.UNKNOWN]

    def name(self) -> str:
        return "chat"

    def description(self) -> str:
        return "General conversation with factory context"
