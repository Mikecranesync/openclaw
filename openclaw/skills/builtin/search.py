"""SearchSkill — web search via Perplexity Sonar API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.skills.base import Skill, SkillContext
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class SearchSkill(Skill):
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self, api_key: str) -> AsyncOpenAI:
        if not self._client:
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai",
            )
        return self._client

    async def handle(self, message: InboundMessage, context: SkillContext) -> OutboundMessage:
        api_key = context.config.perplexity_api_key
        if not api_key:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Web search is not configured. Set PERPLEXITY_API_KEY to enable it.",
            )

        # Strip /search command prefix if present
        query = message.text.strip()
        if query.lower().startswith("/search"):
            query = query[7:].strip()
        if not query:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Please provide a search query. Example: `/search PLC maintenance best practices`",
            )

        client = self._get_client(api_key)
        model = context.config.perplexity_search_model

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": query}],
            )
        except Exception:
            logger.exception("Perplexity search failed for query: %s", query[:80])
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="Web search failed. Please try again.",
            )

        answer = resp.choices[0].message.content or "No results found."
        citations = getattr(resp, "citations", [])

        text = answer
        if citations:
            text += "\n\n**Sources:**\n"
            for i, url in enumerate(citations[:5], 1):
                text += f"{i}. {url}\n"

        logger.info("Perplexity search: query=%s model=%s citations=%d", query[:50], model, len(citations))

        return OutboundMessage(
            channel=message.channel, user_id=message.user_id,
            text=text,
        )

    def intents(self) -> list[Intent]:
        return [Intent.SEARCH]

    def name(self) -> str:
        return "search"

    def description(self) -> str:
        return "Web search powered by Perplexity Sonar API"
