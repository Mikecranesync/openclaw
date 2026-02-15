"""Anthropic provider — Claude for complex analysis."""

from __future__ import annotations

import anthropic

from openclaw.llm.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if not self._client:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> LLMResponse:
        client = self._get_client()
        resp = await client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt or "You are a helpful assistant.",
            messages=messages,
            temperature=temperature,
        )
        text = resp.content[0].text if resp.content else ""
        return LLMResponse(
            text=text,
            model=self._model,
            provider="anthropic",
            tokens_used=(resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0,
        )

    async def complete_with_vision(
        self, messages: list[dict], images: list[bytes],
        system_prompt: str = "", max_tokens: int = 1024,
    ) -> LLMResponse:
        import base64
        client = self._get_client()
        content: list[dict] = []
        for img in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(img).decode()},
            })
        if messages:
            content.append({"type": "text", "text": messages[-1].get("content", "Analyze this image.")})

        resp = await client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": content}],
        )
        text = resp.content[0].text if resp.content else ""
        return LLMResponse(
            text=text, model=self._model, provider="anthropic",
            tokens_used=(resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0,
        )

    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def supports_vision(self) -> bool:
        return True
