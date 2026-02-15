"""WorkOrderSkill — create CMMS work orders via natural language."""

from __future__ import annotations

import json
import logging

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class WorkOrderSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        cmms = context.connectors.get("cmms")
        if not cmms:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="CMMS is not configured. Cannot create work orders.",
            )

        # Use LLM to extract structured WO fields
        response = await context.llm.route(
            Intent.WORK_ORDER,
            messages=[{"role": "user", "content": message.text}],
            system_prompt=(
                "Extract a work order from the user's message. Return JSON with keys: "
                "title (short), description (detailed), priority (HIGH/MEDIUM/LOW)."
            ),
            json_mode=True,
        )

        try:
            wo_data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON for work order extraction: %s", response.text[:200])
            wo_data = {"title": message.text[:100], "description": message.text, "priority": "MEDIUM"}

        result = await cmms.create_work_order(  # type: ignore[attr-defined]
            title=wo_data.get("title", "Untitled"),
            description=wo_data.get("description", ""),
            priority=wo_data.get("priority", "MEDIUM"),
        )

        wo_id = result.get("id", "?")
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=f"Work order created: #{wo_id}\n\n**{wo_data.get('title')}**\nPriority: {wo_data.get('priority')}",
        )

    def intents(self) -> list[Intent]:
        return [Intent.WORK_ORDER]

    def name(self) -> str:
        return "work_order"

    def description(self) -> str:
        return "Create CMMS work orders from natural language"
