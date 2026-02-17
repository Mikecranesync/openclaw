"""WiringEnrichSkill — KB enrichment from component photos.

Hooks into the PHOTO flow to run the 4-stage enrichment pipeline
(ingest → augment → synthesize → upsert) in the background after
normal photo analysis completes.

Also handles explicit /wiring commands for reconstruction.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class WiringEnrichSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        images: list[bytes] = []
        for att in message.attachments:
            if att.type == "image" and att.data:
                images.append(att.data)

        if not images:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Send a component photo to enrich the knowledge base.",
            )

        # Save image to temp file for the enrichment pipeline
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".jpg", prefix="openclaw_enrich_",
        )
        tmp.write(images[0])
        tmp.close()
        photo_path = tmp.name

        caption = message.text or ""
        tags = None
        import re
        tag_match = re.search(r'\b([QKFSMHUTBX]\d+)\b', caption.upper())
        if tag_match:
            tags = tag_match.group(1)

        try:
            from openclaw.wiring.kb_enrichment import enrich_from_photo

            # Run sync enrichment in a thread
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: enrich_from_photo(photo_path, tags=tags),
            )

            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=f"🔧 *KB Enrichment*\n\n{result.summary}",
                parse_mode="markdown",
            )

        except Exception as e:
            logger.exception("Wiring enrichment failed")
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text=f"Enrichment error: {str(e)[:100]}",
            )
        finally:
            try:
                Path(photo_path).unlink(missing_ok=True)
            except Exception:
                pass

    def intents(self) -> list[Intent]:
        return [Intent.KB_ENRICH]

    def name(self) -> str:
        return "wiring_enrich"

    def description(self) -> str:
        return "Enrich knowledge base from component photos"
