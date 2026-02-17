"""DeepSeek provider — OpenAI-compatible API for DeepSeek models."""

from __future__ import annotations

from openai import AsyncOpenAI

from openclaw.llm.base import LLMProvider, LLMResponse


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self._api_key = api_key
        self._model = model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._client:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://api.deepseek.com",
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
            provider="deepseek",
            tokens_used=(resp.usage.total_tokens if resp.usage else 0),
        )

    async def complete_with_vision(
        self, messages: list[dict], images: list[bytes],
        system_prompt: str = "", max_tokens: int = 1024,
    ) -> LLMResponse:
        raise NotImplementedError("DeepSeek does not support vision")

    def name(self) -> str:
        return "deepseek"

    def is_available(self) -> bool:
        return bool(self._api_key)
