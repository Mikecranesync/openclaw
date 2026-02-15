"""StatusSkill — show current PLC tag values."""

from __future__ import annotations

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent


class StatusSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        matrix = context.connectors.get("matrix")
        if not matrix:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Matrix API not configured.",
            )

        tag_rows = await matrix.get_latest_tags(limit=1)  # type: ignore[attr-defined]
        if not tag_rows:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="No tag data available.",
            )

        tags = tag_rows[0] if isinstance(tag_rows, list) else tag_rows
        lines = ["**Equipment Status**", ""]
        skip_keys = {"id", "timestamp", "node_id"}
        for key, value in sorted(tags.items()):
            if key in skip_keys or key.startswith("_"):
                continue
            if isinstance(value, bool) or value in (0, 1):
                display = "ON" if value else "OFF"
            elif isinstance(value, float):
                display = f"{value:.2f}"
            else:
                display = str(value)
            lines.append(f"  {key}: {display}")

        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text="\n".join(lines),
        )

    def intents(self) -> list[Intent]:
        return [Intent.STATUS]

    def name(self) -> str:
        return "status"

    def description(self) -> str:
        return "Show current PLC tag values"
