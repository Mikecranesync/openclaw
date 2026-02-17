"""Maintenance LLM connector — Ollama on PLC laptop for air-gapped inference."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from openclaw.connectors.base import ServiceConnector

logger = logging.getLogger(__name__)


class MaintenanceLLMConnector(ServiceConnector):
    """Connector to Ollama running on the PLC laptop (Layer 1/2 inference)."""

    def __init__(self, base_url: str = "http://100.72.2.99:11434") -> None:
        self._url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._url, timeout=30.0)
        logger.info("MaintenanceLLMConnector targeting %s", self._url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(base_url=self._url, timeout=30.0)
        return self._client

    async def generate(
        self,
        prompt: str,
        model: str = "llama3.2:3b",
        system: str = "",
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Generate a completion from the maintenance LLM.

        Returns dict with 'response' text and metadata.
        """
        client = self._get_client()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        try:
            resp = await client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return {
                "response": data.get("response", ""),
                "model": data.get("model", model),
                "eval_count": data.get("eval_count", 0),
                "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
            }
        except httpx.ConnectError:
            logger.warning("Maintenance LLM unreachable at %s", self._url)
            return {"response": "", "error": "unreachable"}
        except Exception:
            logger.exception("Maintenance LLM generation failed")
            return {"response": "", "error": "generation_failed"}

    async def list_models(self) -> list[str]:
        """List available models on the Ollama instance."""
        client = self._get_client()
        try:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            logger.exception("Failed to list maintenance LLM models")
            return []

    async def health_check(self) -> dict:
        client = self._get_client()
        try:
            resp = await client.get("/")
            if resp.status_code == 200:
                models = await self.list_models()
                return {"status": "healthy", "models": models}
            return {"status": "unhealthy", "code": resp.status_code}
        except httpx.ConnectError:
            return {"status": "unreachable", "url": self._url}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def name(self) -> str:
        return "maintenance_llm"
