"""Aggregated health check across all connectors."""

from __future__ import annotations

from openclaw.connectors.base import ServiceConnector


async def aggregate_health(connectors: dict[str, ServiceConnector]) -> dict:
    results = {}
    all_healthy = True
    for name, connector in connectors.items():
        health = await connector.health_check()
        results[name] = health
        if health.get("status") not in ("healthy", "connected", "disabled"):
            all_healthy = False
    return {"status": "healthy" if all_healthy else "degraded", "connectors": results}
