"""AdminSkill — health checks, budget, connector status, and help."""

from __future__ import annotations

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

HELP_TEXT = (
    "**Jarvis \u2014 What I Can Do**\n"
    "\n"
    "\U0001f50d **Diagnose** \u2014 Ask about faults, alarms, or equipment issues\n"
    '  _"Why is the motor stopped?"_\n'
    "\n"
    "\U0001f4ca **Status** \u2014 Show live PLC tags and I/O\n"
    '  _"Show me IO"_\n'
    "\n"
    "\U0001f4f7 **Photo** \u2014 Analyze equipment from a photo\n"
    "  _Send a photo with or without caption_\n"
    "\n"
    "\U0001f4dd **Diagram** \u2014 Generate wiring diagrams\n"
    '  _"Draw the 220V power feed"_\n'
    "\n"
    "\U0001f50e **Search** \u2014 Look up technical info\n"
    '  _"Search for Micro820 Ethernet setup"_\n'
    "\n"
    "\U0001f4cb **Work Order** \u2014 Create maintenance tasks\n"
    '  _"Create a WO for motor bearing replacement"_\n'
    "\n"
    "\u2699\ufe0f **Admin** \u2014 Health, budget, and system info\n"
    '  _"budget" or "health"_\n'
    "\n"
    "\U0001f4da **KB Enrichment** \u2014 Every photo enriches the knowledge base automatically\n"
    "\n"
    "_Tip: Send a photo of any component to add it to the KB._"
)


class AdminSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        text = message.text.lower().strip()

        # HELP intent — return capabilities guide, not health dump
        if message.intent == Intent.HELP or text in ("help", "/help", "/start"):
            return OutboundMessage(channel=message.channel, user_id=message.user_id, text=HELP_TEXT)

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
        return "System health, budget, connector status, and help"
