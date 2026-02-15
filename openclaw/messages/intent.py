"""Intent classification — rule-based first, LLM fallback."""

from __future__ import annotations

import re

from openclaw.messages.models import InboundMessage
from openclaw.types import Intent

# Keyword patterns for rule-based classification
_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    (re.compile(r"\b(why|stopped|fault|error|alarm|broken|down|diagnos)", re.I), Intent.DIAGNOSE),
    (re.compile(r"\b(status|tags?|reading|current|temp|pressure|running)\b", re.I), Intent.STATUS),
    (re.compile(r"\b(work\s*order|wo|maintenance|repair|schedule)\b", re.I), Intent.WORK_ORDER),
    (re.compile(r"\b(health|budget|admin|restart|config)\b", re.I), Intent.ADMIN),
    (re.compile(r"\b(help|what can you|commands|menu)\b", re.I), Intent.HELP),
]


def classify(message: InboundMessage) -> Intent:
    """Classify message intent using keyword rules."""
    # Photos go to photo skill
    if message.attachments:
        for att in message.attachments:
            if att.type == "image":
                return Intent.PHOTO

    text = message.text.strip()
    if not text:
        return Intent.UNKNOWN

    # Command shortcuts
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        cmd_map = {
            "/diagnose": Intent.DIAGNOSE,
            "/status": Intent.STATUS,
            "/photo": Intent.PHOTO,
            "/wo": Intent.WORK_ORDER,
            "/workorder": Intent.WORK_ORDER,
            "/admin": Intent.ADMIN,
            "/health": Intent.ADMIN,
            "/help": Intent.HELP,
            "/start": Intent.HELP,
        }
        if cmd in cmd_map:
            return cmd_map[cmd]

    # Pattern matching
    for pattern, intent in _PATTERNS:
        if pattern.search(text):
            return intent

    return Intent.CHAT
