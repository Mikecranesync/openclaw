"""NVIDIA provider — Cosmos Reason 2 with Llama 3.1 70B fallback."""

from __future__ import annotations

import httpx

from openclaw.llm.base import LLMProvider, LLMResponse


class NvidiaProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "nvidia/cosmos-reason2-8b",
        fallback_model: str = "meta/llama-3.1-70b-instruct",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._fallback_model = fallback_model
        self._use_fallback = False
        self._base_url = "https://integrate.api.nvidia.com/v1"

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> LLMResponse:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        model = self._fallback_model if self._use_fallback else self._model

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": all_messages,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and not self._use_fallback:
                    self._use_fallback = True
                    return await self.complete(messages, system_prompt, max_tokens, temperature, json_mode)
                raise

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            text=text,
            model=model,
            provider="nvidia",
            tokens_used=usage.get("total_tokens", 0),
            raw=data,
        )

    async def complete_with_vision(
        self, messages: list[dict], images: list[bytes],
        system_prompt: str = "", max_tokens: int = 1024,
    ) -> LLMResponse:
        raise NotImplementedError("NVIDIA vision not implemented in v1")

    def name(self) -> str:
        return "nvidia"

    def is_available(self) -> bool:
        return bool(self._api_key)
