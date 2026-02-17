"""ChatSkill — general conversation with factory context + KB lookup."""

from __future__ import annotations

import logging

from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

# Confidence threshold for KB-only responses (Layer 0 short-circuit)
_KB_HIGH_CONFIDENCE_TYPES = {"procedure", "fault_code", "checklist", "troubleshooting"}


class ChatSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Search KB for relevant knowledge before hitting LLM
        kb_results = await self._search_kb_with_sources(message.text, context)
        kb_context = kb_results["context"]
        kb_sources = kb_results["sources"]

        # Layer 0 short-circuit: if KB has a high-confidence procedural answer,
        # return it directly without burning LLM tokens
        if kb_results["layer0_hit"]:
            response_text = kb_results["layer0_answer"]
            if kb_sources:
                response_text += "\n\n**Sources:**\n" + "\n".join(f"- {s}" for s in kb_sources)
            response_text += "\n\n_Layer 0 (KB direct) | 0ms_"
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=response_text,
            )

        # Build LLM messages with conversation history
        history = message.metadata.get("history", [])
        messages = []
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})

        user_content = message.text
        if kb_context:
            user_content = (
                f"{message.text}\n\n"
                f"RELEVANT KNOWLEDGE BASE ENTRIES:\n{kb_context}\n\n"
                "Use these entries to inform your response when relevant. "
                "Cite specific procedures or known solutions if they apply."
            )
        messages.append({"role": "user", "content": user_content})

        response = await context.llm.route(
            Intent.CHAT,
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
        )

        # Append deterministic Sources block (don't rely on LLM to cite)
        response_text = response.text
        if kb_sources:
            response_text += "\n\n**Sources:**\n" + "\n".join(f"- {s}" for s in kb_sources)

        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response_text,
        )

    async def _search_kb_with_sources(self, query: str, context: SkillContext) -> dict:
        """Search KB and return context, sources, and Layer 0 hit info."""
        result = {
            "context": "",
            "sources": [],
            "layer0_hit": False,
            "layer0_answer": "",
        }

        kb = context.connectors.get("knowledge")
        if not kb or not query or len(query.strip()) < 5:
            return result

        try:
            atoms = await kb.search(query, limit=3)
            if not atoms:
                return result

            lines: list[str] = []
            sources: list[str] = []

            for atom in atoms:
                title = atom.get("title", "")
                atom_type = atom.get("atom_type", "")
                summary = atom.get("summary", "")[:300]
                fixes = atom.get("fixes") or []
                steps = atom.get("steps") or []
                source = atom.get("source_url", "")
                score = atom.get("score", atom.get("similarity", 0))

                lines.append(f"[{atom_type}] {title}")
                lines.append(f"  {summary}")
                if fixes:
                    lines.append(f"  Fixes: {'; '.join(fixes[:3])}")
                if steps:
                    lines.append(f"  Steps: {'; '.join(steps[:3])}")
                if source:
                    lines.append(f"  Source: {source}")
                    sources.append(f"[{title}]({source})")
                elif title:
                    sources.append(title)
                lines.append("")

                # Check for Layer 0 hit: procedural atom with steps/fixes
                if (atom_type in _KB_HIGH_CONFIDENCE_TYPES
                        and (steps or fixes)
                        and (score > 0.85 if score else True)):
                    result["layer0_hit"] = True
                    answer_parts = [f"**{title}**", ""]
                    if summary:
                        answer_parts.append(summary)
                        answer_parts.append("")
                    if steps:
                        answer_parts.append("**Steps:**")
                        for i, step in enumerate(steps, 1):
                            answer_parts.append(f"{i}. {step}")
                        answer_parts.append("")
                    if fixes:
                        answer_parts.append("**Known fixes:**")
                        for fix in fixes:
                            answer_parts.append(f"- {fix}")
                    result["layer0_answer"] = "\n".join(answer_parts)

            result["context"] = "\n".join(lines)
            result["sources"] = sources

        except Exception:
            logger.exception("KB search failed during chat")

        return result

    def intents(self) -> list[Intent]:
        return [Intent.CHAT, Intent.UNKNOWN]

    def name(self) -> str:
        return "chat"

    def description(self) -> str:
        return "General conversation with factory context"
