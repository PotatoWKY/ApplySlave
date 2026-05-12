from __future__ import annotations

import httpx


async def test_health_endpoint_returns_status_fields(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["model_installed"] is False
    assert body["model_name"]
