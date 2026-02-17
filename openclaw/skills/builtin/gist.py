"""GistSkill — generate structured documents and publish as GitHub Gists."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

GIST_SYSTEM_PROMPT = """You are a senior technical writer at an industrial automation company (FactoryLM).

Your job: produce clear, structured markdown documents on demand.

Rules:
1. Output ONLY markdown — no conversational text, no preamble, no "here is your document"
2. Auto-detect document type from the request:
   - PRD (Product Requirements Document)
   - Research / literature review
   - Build guide / tutorial
   - Technical specification
   - Strategy document
   - General write-up
3. Structure with clear headings (##), bullet points, numbered lists, and code blocks where relevant
4. Include an executive summary or TL;DR at the top for longer documents
5. Keep under 3000 words — be concise but thorough
6. Use industrial automation context when relevant (PLCs, SCADA, HMI, Modbus, OPC UA, etc.)
7. Include a metadata header: title, date, author (FactoryLM / Jarvis), document type
"""

# Map keywords to filename prefixes
_PREFIX_MAP = [
    (re.compile(r"\bprd\b", re.I), "PRD_"),
    (re.compile(r"\bresearch\b", re.I), "research_"),
    (re.compile(r"\bbuild\s*guide\b", re.I), "build-guide_"),
    (re.compile(r"\btechnical\s*spec\b", re.I), "spec_"),
    (re.compile(r"\bstrategy\b", re.I), "strategy_"),
    (re.compile(r"\bplaybook\b", re.I), "playbook_"),
    (re.compile(r"\brunbook\b", re.I), "runbook_"),
    (re.compile(r"\barchitecture\b", re.I), "architecture_"),
]


def _infer_filename(prompt: str) -> str:
    """Infer a descriptive filename from the user prompt."""
    prefix = "doc_"
    for pattern, pfx in _PREFIX_MAP:
        if pattern.search(prompt):
            prefix = pfx
            break

    # Extract a slug from the prompt
    # Remove common filler words and the matched prefix keyword
    slug = re.sub(r"[^a-zA-Z0-9\s]", "", prompt)
    slug = re.sub(r"\b(a|an|the|for|of|on|in|to|and|or|with|about|create|write|draft|make|generate)\b", "", slug, flags=re.I)
    slug = slug.strip()
    words = slug.split()[:5]  # Max 5 words in filename
    if not words:
        words = ["document"]
    slug = "-".join(w.lower() for w in words)

    return f"{prefix}{slug}.md"


class GistSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Auth check — same as ShellSkill
        admin_users = [str(uid) for uid in context.config.telegram_allowed_users]
        if admin_users and message.user_id not in admin_users:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Gist creation is restricted to authorized users.",
            )

        # Strip /gist prefix
        text = message.text.strip()
        if text.lower().startswith("/gist"):
            text = text[5:].strip()

        if not text:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text=(
                    "**Gist Skill** — generate documents and publish as GitHub Gists.\n\n"
                    "**Usage:**\n"
                    "- `/gist research industrial IoT protocols`\n"
                    "- `/gist PRD for conveyor monitoring dashboard`\n"
                    "- `/gist build guide for Modbus TCP integration`\n"
                    "- `/gist technical spec for tag caching service`\n"
                    "- `draft a strategy doc for edge AI deployment`\n"
                ),
            )

        # Search KB for context enrichment
        kb_context = await self._search_kb(text, context)

        # Build LLM prompt
        user_prompt = text
        if kb_context:
            user_prompt = f"{text}\n\nRelevant knowledge base context:\n{kb_context}"

        # Call LLM
        try:
            response = await context.llm.route(
                Intent.GIST,
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=GIST_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.4,
            )
        except Exception:
            logger.exception("LLM failed during gist generation")
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Failed to generate document. Please try again.",
            )

        content = response.text
        filename = _infer_filename(text)
        word_count = len(content.split())

        # Write to temp file and create gist
        gist_url = await self._create_gist(content, filename, text)

        if gist_url:
            result_text = (
                f"**Gist created:** {gist_url}\n"
                f"**File:** `{filename}`\n"
                f"**Words:** {word_count}\n"
                f"_Model: {response.model} | {response.latency_ms}ms_"
            )
        else:
            # Fallback: return content inline (content is never lost)
            result_text = (
                f"**{filename}** ({word_count} words)\n"
                f"_Gist upload failed — content inline:_\n\n"
                f"{content}\n\n"
                f"_Model: {response.model} | {response.latency_ms}ms_"
            )

        return OutboundMessage(
            channel=message.channel,
            user_id=message.user_id,
            text=result_text,
        )

    async def _create_gist(self, content: str, filename: str, description: str) -> str | None:
        """Write content to temp file and create a GitHub Gist."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", prefix="gist_", delete=False
            ) as f:
                f.write(content)
                tmp_path = f.name

            desc = description[:200]  # gh limits description length
            proc = await asyncio.create_subprocess_exec(
                "gh", "gist", "create", "--public",
                "--desc", desc,
                "--filename", filename,
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                url = stdout.decode().strip()
                logger.info("Gist created: %s (%s)", url, filename)
                return url
            else:
                logger.error("gh gist create failed: %s", stderr.decode().strip())
                return None
        except Exception:
            logger.exception("Failed to create gist for %s", filename)
            return None
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    async def _search_kb(self, query: str, context: SkillContext) -> str:
        """Search KB for relevant context."""
        kb = context.connectors.get("knowledge")
        if not kb or not query:
            return ""

        try:
            atoms = await kb.search(query, limit=3)
            if not atoms:
                return ""

            lines: list[str] = []
            for atom in atoms:
                title = atom.get("title", "")
                summary = atom.get("summary", "")[:300]
                lines.append(f"- {title}: {summary}")
            return "\n".join(lines)
        except Exception:
            logger.warning("KB search failed during gist generation")
            return ""

    def intents(self) -> list[Intent]:
        return [Intent.GIST]

    def name(self) -> str:
        return "gist"

    def description(self) -> str:
        return "Generate structured documents and publish as GitHub Gists"
