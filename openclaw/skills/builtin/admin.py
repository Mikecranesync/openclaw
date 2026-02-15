"""AdminSkill — health checks, budget, connector status."""

from __future__ import annotations

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent


class AdminSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        text = message.text.lower().strip()

        if "budget" in text:
            summary = context.llm.budget.summary()
            lines = ["**LLM Budget**", ""]
            for provider, data in summary.items():
                limit = data.get("daily_request_limit", 0)
                used = data.get("requests_today", 0)
                status = "within budget" if data.get("within_budget") else "OVER BUDGET"
                lines.append(f"  {provider}: {used}/{limit or 'unlimited'} requests ({status})")
            return OutboundMessage(channel=message.channel, user_id=message.user_id, text="\n".join(lines))

        # Default: health check
        lines = ["**OpenClaw Health**", ""]
        for name, connector in context.connectors.items():
            health = await connector.health_check()
            status = health.get("status", "unknown")
            lines.append(f"  {name}: {status}")

        providers = []
        for name, provider in context.llm.providers.items():
            avail = "available" if provider.is_available() else "no key"
            providers.append(f"  {name}: {avail}")
        lines.append("")
        lines.append("**LLM Providers**")
        lines.extend(providers)

        return OutboundMessage(channel=message.channel, user_id=message.user_id, text="\n".join(lines))

    def intents(self) -> list[Intent]:
        return [Intent.ADMIN, Intent.HELP]

    def name(self) -> str:
        return "admin"

    def description(self) -> str:
        return "System health, budget, and connector status"
