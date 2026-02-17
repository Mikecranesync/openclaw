"""DiagramSkill — generate wiring diagrams for PLC, VFD, motor, and sensor connections."""

from __future__ import annotations

import logging

from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

# Micro820 I/O reference for prompt context
MICRO820_IO_REFERENCE = """
ALLEN-BRADLEY MICRO820 (2080-LC20-20QBB) I/O MAP:
  Digital Inputs:  DI0-DI7 (8 points, 24VDC sink/source)
  Digital Outputs: DO0-DO3 (4 points, relay, 2A max)
  Analog Inputs:   AI0-AI3 (4 points, 0-10V / 4-20mA)
  Analog Outputs:  AO0-AO1 (2 points, 0-10V)
  COM terminals for each group
  Power: 24VDC supply, L1/L2/GND for AC power
"""

# Example wiring diagram format — teaches the LLM the style
WIRING_FORMAT_EXAMPLE = """
EXAMPLE FORMAT (use this exact box-drawing style):

```
MICRO820 PLC                    MAINLINE CONTACTOR           VFD TERMINALS
┌──────────────┐               ┌─────────────────┐         ┌─────────────┐
│              │               │                 │         │             │
│  DO0 ────────┼───────────────┼──► A1 (Coil+)   │         │             │
│              │               │                 │         │             │
│  COM ────────┼───────────────┼──► A2 (Coil-)   │         │             │
│              │               │                 │         │             │
│  DI0 ◄───────┼───────────────┼─── 13 (NO aux)  │         │             │
│              │               │     14 ─► 24V   │         │             │
│              │               │                 │         │             │
│  DO1 ────────┼───────────────┼─────────────────┼─────────┼──► FWD      │
│              │               │                 │         │             │
│  AO0 ────────┼───────────────┼─────────────────┼─────────┼──► VI       │
│              │               │                 │         │  (0-10V)    │
│  AGND ───────┼───────────────┼─────────────────┼─────────┼──► ACM      │
│              │               │                 │         │             │
│  DI1 ◄───────┼───────────────┼─────────────────┼─────────┼─── FA      │
│              │               │                 │         │  (Fault)    │
└──────────────┘               └─────────────────┘         └─────────────┘
```

After the diagram, include:
1. A numbered WIRING SEQUENCE with step-by-step instructions
2. An I/O SUMMARY table: PLC Address | Function | Wired To
3. Safety notes if relevant
"""


class DiagramSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # 1. Search KB for relevant equipment specs
        kb_context = await self._search_kb(message.text, context)

        # 2. Build specialized diagram prompt
        prompt = self._build_prompt(message.text, kb_context)

        # 3. Route to LLM (OpenRouter/Claude for best ASCII art)
        response = await context.llm.route(
            Intent.DIAGRAM,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
        )

        # 4. Format response
        model_tag = f"\n\n_Model: {response.model} | {response.latency_ms}ms_"
        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text + model_tag,
        )

    def _build_prompt(self, question: str, kb_context: str) -> str:
        parts = [
            "Generate a wiring diagram for the following request.",
            "",
            f"REQUEST: {question}",
            "",
            "EQUIPMENT REFERENCE:",
            MICRO820_IO_REFERENCE,
        ]

        if kb_context:
            parts.extend([
                "RELEVANT KNOWLEDGE BASE ENTRIES:",
                kb_context,
                "",
            ])

        parts.extend([
            "DIAGRAM FORMAT INSTRUCTIONS:",
            WIRING_FORMAT_EXAMPLE,
            "",
            "RULES:",
            "1. Draw using ASCII box-drawing characters: ┌─┐│└─┘▼►◄←",
            "2. Show terminal numbers and wire labels on every connection",
            "3. Include power distribution AND control wiring sections",
            "4. After the diagram, provide a numbered WIRING SEQUENCE",
            "5. Include an I/O SUMMARY table",
            "6. Add safety notes where relevant (voltage, current ratings)",
            "7. If the user asks about equipment you know (Micro820, VFD, contactor), use real terminal designations",
            "8. Keep the diagram readable — max 80 characters wide for Telegram",
        ])

        return "\n".join(parts)

    async def _search_kb(self, query: str, context: SkillContext) -> str:
        """Search KB for relevant wiring/equipment info."""
        kb = context.connectors.get("knowledge")
        if not kb or not query:
            return ""

        try:
            atoms = await kb.search(query, limit=3)  # type: ignore[attr-defined]
            if not atoms:
                return ""

            lines: list[str] = []
            for atom in atoms:
                title = atom.get("title", "")
                summary = atom.get("summary", "")[:300]
                lines.append(f"- {title}: {summary}")
            return "\n".join(lines)
        except Exception:
            logger.exception("KB search failed during diagram generation")
            return ""

    def intents(self) -> list[Intent]:
        return [Intent.DIAGRAM]

    def name(self) -> str:
        return "diagram"

    def description(self) -> str:
        return "Generate wiring diagrams for PLC, VFD, motor, and sensor connections"
