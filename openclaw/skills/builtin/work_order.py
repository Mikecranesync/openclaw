"""WorkOrderSkill — create CMMS work orders via natural language.

Falls back to GitHub Gist work orders when no CMMS connector is configured.
"""

from __future__ import annotations

import json
import logging

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class WorkOrderSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Use LLM to extract structured WO fields from natural language
        response = await context.llm.route(
            Intent.WORK_ORDER,
            messages=[{"role": "user", "content": message.text}],
            system_prompt=(
                "Extract a work order from the user's message. Return JSON with keys: "
                "title (short summary), description (detailed), priority (high/medium/low), "
                "asset_name (equipment name if mentioned), asset_id (equipment ID if mentioned), "
                "location (where if mentioned), work_type (Corrective/Preventive/Inspection), "
                "category (Mechanical/Electrical/Instrumentation), failure_code (short code if obvious)."
            ),
            json_mode=True,
        )

        try:
            wo_data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON for work order: %s", response.text[:200])
            wo_data = {"title": message.text[:100], "description": message.text, "priority": "medium"}

        # Normalize priority to lowercase
        wo_data["priority"] = wo_data.get("priority", "medium").lower()

        cmms = context.connectors.get("cmms")
        if cmms:
            # Traditional CMMS connector path
            result = await cmms.create_work_order(
                title=wo_data.get("title", "Untitled"),
                description=wo_data.get("description", ""),
                priority=wo_data.get("priority", "medium"),
            )
            wo_id = result.get("id", "?")
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=f"Work order created: #{wo_id}\n\n**{wo_data.get('title')}**\nPriority: {wo_data.get('priority')}",
            )

        # Gist fallback — create portable work order as GitHub Gist
        try:
            from openclaw.skills.builtin.gist_work_order import create_work_order_gist

            metadata = {
                "title": wo_data.get("title", "Untitled"),
                "description": wo_data.get("description", message.text),
                "status": "open",
                "priority": wo_data.get("priority", "medium"),
                "asset_name": wo_data.get("asset_name", ""),
                "asset_id": wo_data.get("asset_id", ""),
                "location": wo_data.get("location", ""),
                "site": wo_data.get("site", ""),
                "assigned_to": "",
                "work_type": wo_data.get("work_type", ""),
                "category": wo_data.get("category", ""),
                "channel": message.channel or "Telegram",
                "reported_by": message.user_id or "Jarvis",
                "failure_code": wo_data.get("failure_code", ""),
            }

            result = create_work_order_gist(metadata)
            wo_id = metadata["work_order_id"]
            gist_url = result["gist_url"]

            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=(
                    f"Work order created: **{wo_id}**\n\n"
                    f"**{metadata['title']}**\n"
                    f"Priority: {metadata['priority']}\n"
                    f"Status: open\n\n"
                    f"Gist: {gist_url}"
                ),
            )
        except Exception as e:
            logger.exception("Gist work order creation failed")
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=f"Failed to create work order: {e}",
            )

    def intents(self) -> list[Intent]:
        return [Intent.WORK_ORDER]

    def name(self) -> str:
        return "work_order"

    def description(self) -> str:
        return "Create CMMS work orders from natural language (Gist fallback)"
