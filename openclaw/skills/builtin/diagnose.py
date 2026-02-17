"""DiagnoseSkill — the core value: PLC tags + fault rules + KB + LLM = actionable answer."""

from __future__ import annotations

import logging

from openclaw.diagnosis.faults import build_diagnosis_prompt, detect_faults
from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class DiagnoseSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # 1. Pull live tags from Matrix API
        matrix = context.connectors.get("matrix")
        tags: dict = {}
        if matrix:
            tag_rows = await matrix.get_latest_tags(limit=1)  # type: ignore[attr-defined]
            if tag_rows:
                tags = tag_rows[0] if isinstance(tag_rows, list) else tag_rows

        if not tags:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Cannot reach PLC data. Is the Matrix API running?",
            )

        # 2. Rule-based fault detection (zero latency)
        faults = detect_faults(tags)

        # 3. Query Knowledge Base for matching solutions
        kb_context = await self._query_kb(context, faults)

        # 4. Build structured prompt (with KB context if available)
        question = message.text or "Why is this equipment stopped?"
        prompt = build_diagnosis_prompt(question, tags, faults)

        if kb_context:
            prompt += f"\n\nKNOWN SOLUTIONS FROM KNOWLEDGE BASE:\n{kb_context}\n\nUse these known solutions to inform your response when relevant."

        # 5. Route to LLM (Groq primary for speed)
        response = await context.llm.route(
            Intent.DIAGNOSE,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
        )

        # 6. Format response
        model_tag = f"\n\n_Model: {response.model} | {response.latency_ms}ms_"
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text + model_tag,
        )

    async def _query_kb(self, context: SkillContext, faults: list) -> str:
        """Search knowledge base for solutions matching detected faults."""
        kb = context.connectors.get("knowledge")
        if not kb:
            return ""

        kb_lines: list[str] = []
        try:
            for fault in faults:
                if fault.fault_code in ("OK", "IDLE"):
                    continue

                # Search by fault code first
                atoms = await kb.search_by_fault_code(fault.fault_code, limit=2)  # type: ignore[attr-defined]

                # Fall back to full-text search on fault description
                if not atoms:
                    atoms = await kb.search(fault.description, limit=3)  # type: ignore[attr-defined]

                if atoms:
                    kb_lines.append(f"\n[{fault.fault_code}] {fault.title}:")
                    for atom in atoms[:3]:
                        title = atom.get("title", "")
                        summary = atom.get("summary", "")[:200]
                        fixes = atom.get("fixes") or []
                        kb_lines.append(f"  - {title}: {summary}")
                        if fixes:
                            kb_lines.append(f"    Fixes: {'; '.join(fixes[:3])}")
        except Exception:
            logger.exception("KB query failed during diagnosis")

        return "\n".join(kb_lines)

    def intents(self) -> list[Intent]:
        return [Intent.DIAGNOSE]

    def name(self) -> str:
        return "diagnose"

    def description(self) -> str:
        return "Diagnose equipment faults using live PLC data and AI"
