"""PhotoSkill — photo analysis via Gemini Vision + background KB enrichment."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

# Context-aware system prompts based on user intent
PHOTO_SYSTEM_PROMPT_WIRING = (
    "You are an expert industrial electrician analyzing a photo of equipment. "
    "The user wants help creating a wiring diagram. Focus on:\n"
    "1. **Equipment summary** \u2014 one bullet per component (name, model, role)\n"
    "2. **Key connections to trace** \u2014 power, control, comms\n"
    "3. **Wiring priorities** \u2014 what to diagram first\n"
    "4. **Safety notes** \u2014 voltage levels, LOTO reminders\n\n"
    "Keep it SHORT. Use bullet points. No more than 400 words. "
    "Give actionable highlights, not a textbook chapter. "
    "The user is a hands-on technician, not a student."
)

PHOTO_SYSTEM_PROMPT_DIAGNOSE = (
    "You are an expert industrial electrician diagnosing equipment from a photo. "
    "Focus on:\n"
    "1. **Equipment ID** \u2014 manufacturer, model, visible part numbers\n"
    "2. **Visible issues** \u2014 loose wires, damage, incorrect wiring, missing covers\n"
    "3. **Recommended actions** \u2014 what to check or fix next\n\n"
    "Keep it SHORT. Use bullet points. No more than 300 words."
)

PHOTO_SYSTEM_PROMPT_DEFAULT = (
    "You are an expert industrial electrician analyzing equipment from a photo. "
    "Give a CONCISE summary:\n"
    "1. **Equipment list** \u2014 one line per component (manufacturer, model, role)\n"
    "2. **Visible issues** \u2014 anything wrong or noteworthy\n"
    "3. **Next steps** \u2014 what the user should do based on their question\n\n"
    "Keep it SHORT. Use bullet points. No more than 300 words. "
    "Give highlights, not paragraphs."
)


def _pick_system_prompt(caption: str) -> str:
    """Choose the best system prompt based on the user's caption."""
    text = caption.lower()
    if any(kw in text for kw in ("wiring", "diagram", "wire", "connect", "terminal")):
        return PHOTO_SYSTEM_PROMPT_WIRING
    if any(kw in text for kw in ("diagnos", "fault", "issue", "problem", "wrong", "broken", "fix")):
        return PHOTO_SYSTEM_PROMPT_DIAGNOSE
    return PHOTO_SYSTEM_PROMPT_DEFAULT


async def _background_enrich(image_data: bytes, caption: str, send_callback=None, chat_id: str = "") -> None:
    """Run KB enrichment in the background, then notify the user."""
    try:
        import re as _re
        from openclaw.wiring.kb_enrichment import enrich_from_photo

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".jpg", prefix="openclaw_bg_enrich_",
        )
        tmp.write(image_data)
        tmp.close()

        tags = None
        tag_match = _re.search(r"\b([QKFSMHUTBX]\d+)\b", caption.upper())
        if tag_match:
            tags = tag_match.group(1)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: enrich_from_photo(tmp.name, tags=tags, skip_upsert=False),
        )
        logger.info("Background KB enrichment: %s", result.summary)
        Path(tmp.name).unlink(missing_ok=True)

        # Notify the user with the enrichment result
        if send_callback and result.summary and chat_id:
            from openclaw.messages.models import OutboundMessage
            from openclaw.types import Channel
            notify_msg = OutboundMessage(
                channel=Channel.TELEGRAM,
                user_id=chat_id,
                text="\U0001f4da **KB Enrichment**\n" + result.summary,
            )
            await send_callback(notify_msg)
            logger.info("Enrichment notification sent to chat %s", chat_id)
    except Exception:
        logger.warning("Background enrichment failed", exc_info=True)


class PhotoSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        images: list[bytes] = []
        for att in message.attachments:
            if att.type == "image" and att.data:
                images.append(att.data)

        if not images:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="No image found. Send a photo for analysis.",
            )

        caption = message.text or ""
        prompt = caption or "Identify this equipment. Note any visible issues and suggest next steps."
        system_prompt = _pick_system_prompt(caption)

        response = await context.llm.route(
            Intent.PHOTO,
            messages=[{"role": "user", "content": prompt}],
            images=images,
            system_prompt=system_prompt,
            max_tokens=1200,
        )

        # Fire-and-forget: enrich KB in background, notify user when done
        send_cb = getattr(context, "_telegram_send", None)
        asyncio.create_task(
            _background_enrich(images[0], caption, send_callback=send_cb, chat_id=message.user_id)
        )

        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=response.text,
        )

    def intents(self) -> list[Intent]:
        return [Intent.PHOTO]

    def name(self) -> str:
        return "photo"

    def description(self) -> str:
        return "Analyze equipment photos with AI vision + KB enrichment"
