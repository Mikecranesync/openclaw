"""PhotoSkill — photo analysis via Gemini Vision."""

from __future__ import annotations

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent


class PhotoSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        images: list[bytes] = []
        for att in message.attachments:
            if att.type == "image" and att.data:
                images.append(att.data)

        if not images:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="No image found. Send a photo for analysis.",
            )

        prompt = message.text or "Identify this equipment. What is it? Note any visible defects or issues."
        response = await context.llm.route(
            Intent.PHOTO,
            messages=[{"role": "user", "content": prompt}],
            images=images,
            system_prompt="You are an industrial equipment identification expert. Identify the equipment manufacturer, model, and any visible issues.",
        )

        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text,
        )

    def intents(self) -> list[Intent]:
        return [Intent.PHOTO]

    def name(self) -> str:
        return "photo"

    def description(self) -> str:
        return "Analyze equipment photos with AI vision"
