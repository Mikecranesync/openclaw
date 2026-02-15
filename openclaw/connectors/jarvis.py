"""Jarvis Node connector — remote shell execution."""

from __future__ import annotations

import httpx

from openclaw.connectors.base import ServiceConnector


class JarvisConnector(ServiceConnector):
    def __init__(self, hosts: dict[str, str] | None = None) -> None:
        self._hosts = hosts or {}
        self._clients: dict[str, httpx.AsyncClient] = {}

    async def connect(self) -> None:
        for label, url in self._hosts.items():
            self._clients[label] = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=30.0)

    async def disconnect(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    async def execute(self, command: str, host: str | None = None, timeout: int = 30) -> dict:
        client = self._resolve_client(host)
        resp = await client.post("/shell", json={"command": command, "timeout": timeout})
        resp.raise_for_status()
        return resp.json()

    async def read_file(self, path: str, host: str | None = None) -> str:
        client = self._resolve_client(host)
        resp = await client.post("/files/read", json={"path": path})
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", "")

    def _resolve_client(self, host: str | None) -> httpx.AsyncClient:
        if host and host in self._clients:
            return self._clients[host]
        if self._clients:
            return next(iter(self._clients.values()))
        raise RuntimeError("No Jarvis hosts configured")

    async def health_check(self) -> dict:
        results = {}
        for label, client in self._clients.items():
            try:
                resp = await client.get("/health")
                results[label] = {"status": "healthy", "code": resp.status_code}
            except Exception as e:
                results[label] = {"status": "unhealthy", "error": str(e)}
        return results

    def name(self) -> str:
        return "jarvis"
