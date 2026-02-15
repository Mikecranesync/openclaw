"""CMMS connector — assets and work orders."""

from __future__ import annotations

import httpx

from openclaw.connectors.base import ServiceConnector


class CMMSConnector(ServiceConnector):
    def __init__(self, url: str, email: str = "", password: str = "") -> None:
        self._url = url.rstrip("/")
        self._email = email
        self._password = password
        self._token: str = ""
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._url, timeout=15.0)
        if self._email and self._password:
            await self._login()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(base_url=self._url, timeout=15.0)
        return self._client

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _login(self) -> None:
        client = self._get_client()
        resp = await client.post(
            "/auth/signin",
            json={"email": self._email, "password": self._password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("accessToken", data.get("token", ""))

    async def create_work_order(
        self, title: str, description: str, priority: str = "MEDIUM", asset_id: int | None = None
    ) -> dict:
        client = self._get_client()
        body: dict = {"title": title, "description": description, "priority": priority}
        if asset_id:
            body["asset"] = {"id": asset_id}
        resp = await client.post("/api/work-orders", json=body, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def list_assets(self) -> list[dict]:
        client = self._get_client()
        resp = await client.get("/api/assets", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> dict:
        try:
            client = self._get_client()
            resp = await client.get("/")
            return {"status": "healthy", "code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def name(self) -> str:
        return "cmms"
