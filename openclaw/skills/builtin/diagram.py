"""DiagramSkill — generate spec-driven wiring diagrams as PNG images.

Replaces ASCII art with professional IEC 60617 diagrams rendered via
the openclaw.diagram engine. The LLM generates a structured JSON spec;
the WiringRenderer turns it into SVG -> PNG.
"""

from __future__ import annotations

import json
import logging

from openclaw.diagram.renderer import WiringRenderer, render_markdown_summary
from openclaw.diagram.schema import DiagramSpec
from openclaw.llm.prompts import SYSTEM_PROMPT
from openclaw.messages.models import Attachment, InboundMessage, OutboundMessage
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

# JSON spec schema reference for LLM
SPEC_SCHEMA_PROMPT = """
You MUST respond with a valid JSON object matching this schema. No markdown, no backticks, no explanation — ONLY the JSON.

{
  "title": "Drawing title",
  "drawing_number": "FLM-WD-001",
  "revision": "A",
  "standard": "IEC",
  "description": "Brief description",
  "notes": ["Note 1", "Note 2"],
  "components": [
    {
      "tag": "Q1",
      "type": "circuit_breaker",
      "label": "Main Circuit Breaker",
      "ratings": {"voltage": "400V", "current": "25A"},
      "terminals": [{"id": "1", "label": "Line", "side": "top"}, {"id": "2", "label": "Load", "side": "bottom"}],
      "group": "motor_starter",
      "position_hint": "top"
    }
  ],
  "connections": [
    {"from": "Q1.2", "to": "K1.1", "wire_label": "L1", "wire_type": "power"}
  ],
  "buses": [
    {"name": "L1", "type": "power", "orientation": "horizontal"}
  ],
  "layout": {"power_flow": "top-to-bottom", "control_flow": "left-to-right"}
}

VALID component types: motor_3ph, motor_1ph, contactor_3pole, contactor_coil,
overload_relay, circuit_breaker, fuse, pushbutton_no, pushbutton_nc,
emergency_stop, terminal_block, plc_input_card, plc_output_card, vfd,
transformer, indicator_light, proximity_sensor, relay_coil,
relay_contact_no, relay_contact_nc

VALID wire_type: power, control, signal, earth, neutral
VALID bus type: power, control, earth, neutral

RULES:
1. Use ONLY real terminal designations from the reference material.
2. Every connection must reference valid component tags and terminal IDs.
3. Include power buses (L1, L2, L3) for 3-phase circuits.
4. Include control buses (+24V, 0V) for control circuits.
5. Add PE (earth) bus when motors are involved.
6. Add safety notes (voltage, current, overload settings).
7. Keep it practical — real-world component ratings.
"""


class DiagramSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        query = message.text.strip()
        if not query or query in ("/diagram", "/wiring"):
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text=(
                    "**Wiring Diagram Generator**\n\n"
                    "Send a description of the circuit you need.\n\n"
                    "Examples:\n"
                    "- `/diagram DOL motor starter 11kW`\n"
                    "- `/diagram star-delta starter for pump`\n"
                    "- `/diagram VFD wiring for conveyor`\n"
                    "- `/diagram Micro820 to contactor`\n"
                    "- `draw me a wiring diagram for an e-stop circuit`\n"
                ),
            )

        # 1. Search KB for relevant Eaton/equipment specs
        kb_context = await self._search_kb(query, context)
        kb_sources: list[str] = []

        # 2. Build LLM prompt to generate JSON spec
        prompt = self._build_spec_prompt(query, kb_context)

        # 3. Call LLM with json_mode for structured output
        messages = [{"role": "user", "content": prompt}]
        try:
            response = await context.llm.route(
                Intent.DIAGRAM,
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                json_mode=True,
                max_tokens=2048,
                temperature=0.2,
            )
        except Exception:
            logger.exception("LLM call failed for diagram spec generation")
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Failed to generate diagram spec. Please try again.",
            )

        # 4. Parse JSON response into DiagramSpec (with one retry on parse failure)
        try:
            spec_json = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse failed on first attempt: %s — retrying", e)
            # Retry once: ask LLM to fix its JSON
            retry_messages = messages + [
                {"role": "assistant", "content": response.text},
                {"role": "user", "content": f"Your JSON was invalid: {e}. Return ONLY valid JSON, no markdown."},
            ]
            try:
                response = await context.llm.route(
                    Intent.DIAGRAM,
                    messages=retry_messages,
                    system_prompt=SYSTEM_PROMPT,
                    json_mode=True,
                    max_tokens=2048,
                    temperature=0.1,
                )
                spec_json = json.loads(response.text)
            except (json.JSONDecodeError, Exception) as retry_err:
                logger.error("JSON retry also failed: %s\nRaw: %s", retry_err, response.text[:500])
                return OutboundMessage(
                    channel=message.channel,
                    user_id=message.user_id,
                    text=f"Diagram spec generation produced invalid JSON after retry. Raw output:\n\n```\n{response.text[:2000]}\n```",
                )

        try:
            spec = DiagramSpec.model_validate(spec_json)
        except Exception as e:
            logger.error("DiagramSpec validation failed: %s", e)
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text=f"Diagram spec validation failed: {e}",
            )

        # 5. Render to PNG
        try:
            renderer = WiringRenderer(spec)
            png_bytes = renderer.render_png()
        except Exception as e:
            logger.exception("PNG rendering failed")
            # Fall back to markdown summary only
            summary = render_markdown_summary(spec)
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text=f"{summary}\n\n_PNG rendering failed: {e}_",
            )

        # 6. Build markdown summary
        summary = render_markdown_summary(spec)

        # Add KB sources if available
        if kb_sources:
            summary += "\n\n**Sources:**\n" + "\n".join(f"- {s}" for s in kb_sources)

        model_tag = f"\n\n_Diagram generated from spec | {response.model} | {response.latency_ms}ms_"

        # 7. Return with PNG attachment
        return OutboundMessage(
            channel=message.channel,
            user_id=message.user_id,
            text=summary + model_tag,
            attachments=[
                Attachment(
                    type="image",
                    data=png_bytes,
                    mime_type="image/png",
                    filename=f"{spec.drawing_number}.png",
                )
            ],
        )

    def _build_spec_prompt(self, question: str, kb_context: str) -> str:
        """Build the LLM prompt that generates a DiagramSpec JSON."""
        parts = [
            "Generate a wiring diagram specification as a JSON object.",
            "",
            f"REQUEST: {question}",
            "",
            "EQUIPMENT REFERENCE:",
            MICRO820_IO_REFERENCE,
        ]

        if kb_context:
            parts.extend([
                "",
                "RELEVANT KNOWLEDGE BASE ENTRIES (use real terminal designations from these):",
                kb_context,
            ])

        parts.extend([
            "",
            "OUTPUT FORMAT:",
            SPEC_SCHEMA_PROMPT,
        ])

        return "\n".join(parts)

    async def _search_kb(self, query: str, context: SkillContext) -> str:
        """Search KB for relevant wiring/equipment info."""
        kb = context.connectors.get("knowledge")
        if not kb or not query:
            return ""

        try:
            atoms = await kb.search(query, limit=5)
            if not atoms:
                return ""

            lines: list[str] = []
            for atom in atoms:
                title = atom.get("title", "")
                summary = atom.get("summary", "")[:400]
                content = atom.get("content", "")[:600]
                atom_type = atom.get("atom_type", "")
                source = atom.get("source_url", "")
                pages = atom.get("source_pages", "")

                entry = f"[{atom_type}] {title}"
                if pages:
                    entry += f" (p.{pages})"
                entry += f"\n{summary}"
                if content and content != summary:
                    entry += f"\n{content[:300]}"
                lines.append(entry)

            return "\n\n".join(lines)
        except Exception:
            logger.exception("KB search failed during diagram generation")
            return ""

    def intents(self) -> list[Intent]:
        return [Intent.DIAGRAM]

    def name(self) -> str:
        return "diagram"

    def description(self) -> str:
        return "Generate professional IEC 60617 wiring diagrams as PNG images"
