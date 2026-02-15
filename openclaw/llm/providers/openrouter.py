"""OpenRouter provider — unified access to 300+ models."""

from __future__ import annotations

from openai import AsyncOpenAI

from openclaw.llm.base import LLMProvider, LLMResponse


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "anthropic/claude-sonnet-4") -> None:
        self._api_key = api_key
        self._model = model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._client:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/Mikecranesync/openclaw",
                    "X-Title": "OpenClaw",
                },
            )
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
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        kwargs: dict = {
            "model": self._model,
            "messages": all_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            model=self._model,
            provider="openrouter",
            tokens_used=(resp.usage.total_tokens if resp.usage else 0),
        )

    async def complete_with_vision(
        self, messages: list[dict], images: list[bytes],
        system_prompt: str = "", max_tokens: int = 1024,
    ) -> LLMResponse:
        import base64
        client = self._get_client()
        content: list[dict] = []
        for img in images:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        if messages:
            content.append({"type": "text", "text": messages[-1].get("content", "Analyze this image.")})

        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.append({"role": "user", "content": content})

        resp = await client.chat.completions.create(model=self._model, messages=all_messages, max_tokens=max_tokens)
        choice = resp.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            model=self._model, provider="openrouter",
            tokens_used=(resp.usage.total_tokens if resp.usage else 0),
        )

    def name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def supports_vision(self) -> bool:
        return True
