"""Intent classification — rule-based first, LLM fallback."""

from __future__ import annotations

import re

from openclaw.messages.models import InboundMessage
from openclaw.types import Intent

# Keyword patterns for rule-based classification
# Order matters: first match wins. More specific patterns go first.
_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    # WORK_ORDER — highest priority when explicitly requested
    (re.compile(r"\b(work\s*order|open\s+a?\s*wo\b|create\s+a?\s*wo\b)", re.I), Intent.WORK_ORDER),

    # DIAGRAM — specific equipment terms
    (re.compile(r"\b(wiring|diagram|schematic|blueprint|draw(?:ing)?|circuit|print(?:s)?|redraw|re-draw)\b", re.I), Intent.DIAGRAM),
    (re.compile(r"\b(update|redo|fix|change|modify|add\s+\w+\s+to)\b.{0,30}\b(print|diagram|drawing|schematic)\b", re.I), Intent.DIAGRAM),

    # PROJECT — scaffold/build requests
    (re.compile(r"\b(scaffold|build\s+me\b|create\s+a\s+project|start\s+a\s+new|bootstrap|starter\s*kit|boilerplate)\b", re.I), Intent.PROJECT),

    # GIST — document generation
    (re.compile(r"\b(gist|write\s*up|draft\s+a\b|prd\s+for|technical\s+spec|build\s+guide|strategy\s+doc|save\s+.+as\s+gist)\b", re.I), Intent.GIST),

    # DIAGNOSE — specific fault words (always factory-related)
    (re.compile(r"\b(fault|alarm|broken|diagnos)\b", re.I), Intent.DIAGNOSE),
    # DIAGNOSE — "why" only with equipment/fault context nearby
    (re.compile(r"\bwhy\b.{0,30}\b(stopped|fault|error|alarm|broken|down|not\s+(?:working|running|starting))\b", re.I), Intent.DIAGNOSE),
    # DIAGNOSE — equipment word + stopped/down (bidirectional)
    (re.compile(r"\b(motor|conveyor|equipment|machine|line|plc|vfd|pump|compressor)\b.{0,30}\b(stopped|down|error)\b", re.I), Intent.DIAGNOSE),
    (re.compile(r"\b(stopped|down|error)\b.{0,30}\b(motor|conveyor|equipment|machine|line|plc|vfd|pump|compressor)\b", re.I), Intent.DIAGNOSE),

    # STATUS — removed "current" (too ambiguous in general English)
    (re.compile(r"\b(status|tags?|reading|temp|pressure|running|show\s+(?:me\s+)?io|live\s+io|plc\s+io|\bio\b)\b", re.I), Intent.STATUS),

    # WORK_ORDER — removed "repair" (ambiguous: "how to repair?" is a KB question)
    (re.compile(r"\b(work\s*order|wo\b|maintenance|schedule)\b", re.I), Intent.WORK_ORDER),

    # ADMIN
    (re.compile(r"\b(health|budget|admin|restart|config)\b", re.I), Intent.ADMIN),

    # HELP
    (re.compile(r"^\/?(help|commands|menu)$|^what can you\b", re.I), Intent.HELP),

    # SEARCH
    (re.compile(r"\b(search|look\s*up|find\s+(?:out|info)|google|web\s*search)\b", re.I), Intent.SEARCH),

    # SHELL
    (re.compile(r"^\$\s+|^\s*(?:run|execute|shell)\s+", re.I), Intent.SHELL),
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
            "/diagram": Intent.DIAGRAM,
            "/wiring": Intent.DIAGRAM,
            "/diagnose": Intent.DIAGNOSE,
            "/status": Intent.STATUS,
            "/photo": Intent.PHOTO,
            "/wo": Intent.WORK_ORDER,
            "/workorder": Intent.WORK_ORDER,
            "/admin": Intent.ADMIN,
            "/health": Intent.ADMIN,
            "/help": Intent.HELP,
            "/start": Intent.HELP,
            "/search": Intent.SEARCH,
            "/run": Intent.SHELL,
            "/gist": Intent.GIST,
            "/project": Intent.PROJECT,
        }
        if cmd in cmd_map:
            return cmd_map[cmd]

    # Pattern matching
    for pattern, intent in _PATTERNS:
        if pattern.search(text):
            return intent

    return Intent.CHAT
