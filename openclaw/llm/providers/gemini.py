"""Gemini provider — Google Gemini Flash for vision/photo analysis."""

from __future__ import annotations

import google.generativeai as genai

from openclaw.llm.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._api_key = api_key
        self._model_name = model
        self._configured = False

    def _ensure_configured(self) -> None:
        if not self._configured:
            genai.configure(api_key=self._api_key)
            self._configured = True

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> LLMResponse:
        self._ensure_configured()
        model = genai.GenerativeModel(self._model_name)
        prompt = system_prompt + "\n\n" if system_prompt else ""
        for msg in messages:
            prompt += msg.get("content", "") + "\n"

        resp = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=temperature),
        )
        return LLMResponse(
            text=resp.text or "",
            model=self._model_name,
            provider="gemini",
        )

    async def complete_with_vision(
        self, messages: list[dict], images: list[bytes],
        system_prompt: str = "", max_tokens: int = 1024,
    ) -> LLMResponse:
        self._ensure_configured()
        model = genai.GenerativeModel(self._model_name)
        parts: list = []
        for img_bytes in images:
            parts.append({"mime_type": "image/jpeg", "data": img_bytes})
        text_prompt = system_prompt + "\n" if system_prompt else ""
        if messages:
            text_prompt += messages[-1].get("content", "Analyze this image.")
        parts.append(text_prompt)

        resp = model.generate_content(parts)
        return LLMResponse(
            text=resp.text or "",
            model=self._model_name,
            provider="gemini",
        )

    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def supports_vision(self) -> bool:
        return True
