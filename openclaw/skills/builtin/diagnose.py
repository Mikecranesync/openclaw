"""DiagnoseSkill — the core value: PLC tags + fault rules + LLM = actionable answer."""

from __future__ import annotations

from openclaw.diagnosis.faults import build_diagnosis_prompt, detect_faults
from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent


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

        # 3. Build structured prompt
        question = message.text or "Why is this equipment stopped?"
        prompt = build_diagnosis_prompt(question, tags, faults)

        # 4. Route to LLM (Groq primary for speed)
        response = await context.llm.route(
            Intent.DIAGNOSE,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
        )

        # 5. Format response
        model_tag = f"\n\n_Model: {response.model} | {response.latency_ms}ms_"
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text + model_tag,
        )

    def intents(self) -> list[Intent]:
        return [Intent.DIAGNOSE]

    def name(self) -> str:
        return "diagnose"

    def description(self) -> str:
        return "Diagnose equipment faults using live PLC data and AI"
