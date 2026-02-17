"""ChatSkill — general conversation with factory context + KB lookup."""

from __future__ import annotations

import logging

from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class ChatSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Search KB for relevant knowledge before hitting LLM
        kb_context = await self._search_kb(message.text, context)

        user_content = message.text
        if kb_context:
            user_content = (
                f"{message.text}\n\n"
                f"RELEVANT KNOWLEDGE BASE ENTRIES:\n{kb_context}\n\n"
                "Use these entries to inform your response when relevant. "
                "Cite specific procedures or known solutions if they apply."
            )

        response = await context.llm.route(
            Intent.CHAT,
            messages=[{"role": "user", "content": user_content}],
            system_prompt=SYSTEM_PROMPT,
        )
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text,
        )

    async def _search_kb(self, query: str, context: SkillContext) -> str:
        """Quick KB search — include results if relevant."""
        kb = context.connectors.get("knowledge")
        if not kb or not query or len(query.strip()) < 5:
            return ""

        try:
            atoms = await kb.search(query, limit=3)  # type: ignore[attr-defined]
            if not atoms:
                return ""

            lines: list[str] = []
            for atom in atoms:
                title = atom.get("title", "")
                atom_type = atom.get("atom_type", "")
                summary = atom.get("summary", "")[:300]
                fixes = atom.get("fixes") or []
                steps = atom.get("steps") or []

                lines.append(f"[{atom_type}] {title}")
                lines.append(f"  {summary}")
                if fixes:
                    lines.append(f"  Fixes: {'; '.join(fixes[:3])}")
                if steps:
                    lines.append(f"  Steps: {'; '.join(steps[:3])}")
                source = atom.get("source_url", "")
                if source:
                    lines.append(f"  Source: {source}")
                lines.append("")

            return "\n".join(lines)
        except Exception:
            logger.exception("KB search failed during chat")
            return ""

    def intents(self) -> list[Intent]:
        return [Intent.CHAT, Intent.UNKNOWN]

    def name(self) -> str:
        return "chat"

    def description(self) -> str:
        return "General conversation with factory context"
