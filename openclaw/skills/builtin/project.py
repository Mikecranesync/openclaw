"""ProjectSkill — scaffold multi-file projects and publish as GitHub Gists."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)

MAX_FILES = 8  # Budget protection — max 9 LLM calls total (1 plan + 8 files)

PROJECT_PLAN_PROMPT = (
    "You are a senior software architect at FactoryLM, an industrial automation AI company.\n\n"
    "Your job: design a project scaffold based on the user's request.\n\n"
    "Output ONLY valid JSON with this exact schema — no markdown fences, no commentary:\n"
    '{"title": "short project title", "description": "1-2 sentence description", '
    '"tech_stack": ["python", "fastapi"], '
    '"files": [{"filename": "README.md", "description": "Project overview with setup instructions"}, '
    '{"filename": "main.py", "description": "Application entry point"}, '
    '{"filename": "requirements.txt", "description": "Python dependencies"}]}\n\n'
    "Rules:\n"
    "1. Always include README.md as the first file\n"
    "2. Include a dependency manifest (requirements.txt, package.json, go.mod, etc.)\n"
    "3. Include .gitignore appropriate for the tech stack\n"
    "4. 3-8 files total — enough to be useful, not overwhelming\n"
    "5. Infer the tech stack from the request (default to Python if ambiguous)\n"
    "6. Include functional code structure, not just stubs\n"
    "7. Use industrial automation context when relevant (PLCs, Modbus, MQTT, OPC UA)"
)

PROJECT_FILE_PROMPT = (
    "You are a senior developer at FactoryLM.\n\n"
    "Project context:\n"
    "- Title: {title}\n"
    "- Description: {description}\n"
    "- Tech stack: {tech_stack}\n\n"
    "Generate the file: {filename}\n"
    "Purpose: {file_description}\n\n"
    "Rules:\n"
    "1. Output ONLY the file content — no markdown fences, no explanation\n"
    "2. Write functional, production-quality code with helpful comments\n"
    "3. Keep under 150 lines\n"
    "4. Use modern best practices for the tech stack\n"
    "5. Include proper imports, error handling, and type hints where applicable"
)


class ProjectSkill(Skill):
    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        # Auth check
        admin_users = [str(uid) for uid in context.config.telegram_allowed_users]
        if admin_users and message.user_id not in admin_users:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Project creation is restricted to authorized users.",
            )

        # Strip /project prefix
        text = message.text.strip()
        if text.lower().startswith("/project"):
            text = text[8:].strip()

        # Also strip common natural-language prefixes
        for prefix in ("scaffold ", "build me ", "bootstrap "):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text=(
                    "**Project Skill** — scaffold multi-file projects as GitHub Gists.\n\n"
                    "**Usage:**\n"
                    "- `/project FastAPI service for PLC tag monitoring`\n"
                    "- `/project Python CLI for Modbus scanning`\n"
                    "- `build me a Telegram bot for factory alerts`\n"
                    "- `scaffold a React dashboard for conveyor status`\n"
                ),
            )

        # Search KB for context
        kb_context = await self._search_kb(text, context)

        # Phase 1: Generate project plan (JSON)
        plan_prompt = text
        if kb_context:
            plan_prompt = f"{text}\n\nRelevant knowledge base context:\n{kb_context}"

        try:
            plan_response = await context.llm.route(
                Intent.PROJECT,
                messages=[{"role": "user", "content": plan_prompt}],
                system_prompt=PROJECT_PLAN_PROMPT,
                max_tokens=1024,
                temperature=0.3,
                json_mode=True,
            )
        except Exception:
            logger.exception("LLM failed during project planning")
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Failed to plan project. Please try again.",
            )

        # Parse the plan JSON
        spec = self._parse_plan(plan_response.text)
        if spec is None:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Could not parse project plan. Please rephrase your request.",
            )

        title = spec.get("title", "Untitled Project")
        description = spec.get("description", "")
        tech_stack = spec.get("tech_stack", [])
        files_spec = spec.get("files", [])[:MAX_FILES]

        if not files_spec:
            return OutboundMessage(
                channel=message.channel,
                user_id=message.user_id,
                text="Project plan contained no files. Please try again with more detail.",
            )

        # Phase 2: Generate each file
        generated_files: dict[str, str] = {}
        errors: list[str] = []

        for file_info in files_spec:
            fname = file_info.get("filename", "unknown.txt")
            fdesc = file_info.get("description", "")

            file_prompt = PROJECT_FILE_PROMPT.format(
                title=title,
                description=description,
                tech_stack=", ".join(tech_stack),
                filename=fname,
                file_description=fdesc,
            )

            try:
                file_response = await context.llm.route(
                    Intent.PROJECT,
                    messages=[{"role": "user", "content": file_prompt}],
                    system_prompt="",
                    max_tokens=2048,
                    temperature=0.3,
                )
                content = file_response.text
                # Strip markdown fences if the LLM wrapped the content
                content = self._strip_fences(content)
                generated_files[fname] = content
            except Exception:
                logger.exception("Failed to generate file: %s", fname)
                generated_files[fname] = f"# Error: failed to generate {fname}\n"
                errors.append(fname)

        # Create multi-file gist
        gist_url = await self._create_multi_gist(generated_files, f"{title}: {description}")

        # Build response
        file_list = "\n".join(f"  - `{f}`" for f in generated_files)
        stack_str = ", ".join(tech_stack) if tech_stack else "not specified"

        if gist_url:
            result_text = (
                f"**Project scaffolded:** {gist_url}\n\n"
                f"**{title}**\n"
                f"{description}\n\n"
                f"**Tech stack:** {stack_str}\n"
                f"**Files ({len(generated_files)}):**\n{file_list}"
            )
        else:
            # Fallback: list file names and sizes
            size_list = "\n".join(
                f"  - `{f}` ({len(c)} chars)" for f, c in generated_files.items()
            )
            result_text = (
                f"**{title}**\n"
                f"{description}\n\n"
                f"_Gist upload failed — files generated but not published:_\n"
                f"**Files ({len(generated_files)}):**\n{size_list}"
            )

        if errors:
            result_text += f"\n\n_Partial failures: {', '.join(errors)}_"

        return OutboundMessage(
            channel=message.channel,
            user_id=message.user_id,
            text=result_text,
        )

    def _parse_plan(self, text: str) -> dict | None:
        """Parse JSON plan from LLM response, stripping fences if present."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown JSON fences
        stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
        stripped = re.sub(r"\n?```\s*$", "", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            logger.error("Failed to parse project plan JSON: %s", text[:200])
            return None

    def _strip_fences(self, text: str) -> str:
        """Strip markdown code fences from generated file content."""
        text = text.strip()
        if text.startswith("```"):
            # Remove opening fence (with optional language tag)
            text = re.sub(r"^```\w*\s*\n?", "", text)
            # Remove closing fence
            text = re.sub(r"\n?```\s*$", "", text)
        return text

    async def _create_multi_gist(self, files: dict[str, str], description: str) -> str | None:
        """Write files to temp dir and create a multi-file GitHub Gist."""
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="project_")
            file_paths = []

            for filename, content in files.items():
                # Sanitize filename — no path traversal
                safe_name = Path(filename).name
                file_path = Path(tmp_dir) / safe_name
                file_path.write_text(content)
                file_paths.append(str(file_path))

            desc = description[:200]
            cmd = ["gh", "gist", "create", "--public", "--desc", desc] + file_paths

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                url = stdout.decode().strip()
                logger.info("Multi-file gist created: %s (%d files)", url, len(files))
                return url
            else:
                logger.error("gh gist create failed: %s", stderr.decode().strip())
                return None
        except Exception:
            logger.exception("Failed to create multi-file gist")
            return None
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

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
            logger.warning("KB search failed during project generation")
            return ""

    def intents(self) -> list[Intent]:
        return [Intent.PROJECT]

    def name(self) -> str:
        return "project"

    def description(self) -> str:
        return "Scaffold multi-file projects and publish as GitHub Gists"
