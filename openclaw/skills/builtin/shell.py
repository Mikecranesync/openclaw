"""ShellSkill — execute commands on connected machines via JarvisConnector."""

from __future__ import annotations

import logging
import re

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

# Pattern to extract @host target from command text
_HOST_RE = re.compile(r"@(plc|travel)\s+", re.I)

# Host label aliases
_HOST_ALIASES = {
    "plc": "plc",
    "travel": "travel",
}


class ShellSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Auth: only allowed users can run shell commands
        admin_users = [str(uid) for uid in context.config.telegram_allowed_users]
        if admin_users and message.user_id not in admin_users:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Shell access is restricted to admin users.",
            )

        # Extract command from message text
        text = message.text.strip()

        # Strip /run prefix
        if text.lower().startswith("/run"):
            text = text[4:].strip()

        # Strip $ prefix
        if text.startswith("$"):
            text = text[1:].strip()

        # Extract @host target
        host = None
        match = _HOST_RE.search(text)
        if match:
            alias = match.group(1).lower()
            host = _HOST_ALIASES.get(alias, alias)
            text = text[:match.start()] + text[match.end():]
            text = text.strip()

        if not text:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Usage: `$ <command>` or `/run <command>`\nTarget a host: `$ @plc ls /home`",
            )

        # Execute via JarvisConnector
        jarvis = context.connectors.get("jarvis")
        if not jarvis:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="No Jarvis hosts configured. Check `jarvis_hosts` in openclaw.yaml.",
            )

        try:
            result = await jarvis.execute(text, host=host)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", result.get("returncode", None))

            parts = []
            if stdout:
                parts.append(f"```\n{stdout.rstrip()}\n```")
            if stderr:
                parts.append(f"**stderr:**\n```\n{stderr.rstrip()}\n```")
            if exit_code is not None and exit_code != 0:
                parts.append(f"Exit code: {exit_code}")

            response_text = "\n".join(parts) if parts else "_Command completed with no output._"
            if host:
                response_text = f"**@{host}**\n{response_text}"
        except Exception as e:
            logger.exception("Shell execution failed: %s", text)
            response_text = f"Shell error: `{e}`"

        return OutboundMessage(
            channel=message.channel,
            user_id=message.user_id,
            text=response_text,
        )

    def intents(self) -> list[Intent]:
        return [Intent.SHELL]

    def name(self) -> str:
        return "shell"

    def description(self) -> str:
        return "Execute shell commands on connected machines"
