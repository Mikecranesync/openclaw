"""Matrix API connector — tags, incidents, insights."""

from __future__ import annotations

import httpx

from openclaw.connectors.base import ServiceConnector


class MatrixConnector(ServiceConnector):
    def __init__(self, url: str = "http://localhost:8000") -> None:
        self._url = url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._url, timeout=10.0)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(base_url=self._url, timeout=10.0)
        return self._client

    async def get_latest_tags(self, node_id: str | None = None, limit: int = 1) -> list[dict]:
        client = self._get_client()
        params: dict = {"limit": limit}
        if node_id:
            params["node_id"] = node_id
        resp = await client.get("/api/tags", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_incidents(self, status: str = "open", limit: int = 20) -> list[dict]:
        client = self._get_client()
        resp = await client.get("/api/incidents", params={"status": status, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    async def post_insight(self, insight: dict) -> dict:
        client = self._get_client()
        resp = await client.post("/api/insights", json=insight)
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> dict:
        try:
            client = self._get_client()
            resp = await client.get("/api/health")
            return {"status": "healthy", "code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def name(self) -> str:
        return "matrix"
