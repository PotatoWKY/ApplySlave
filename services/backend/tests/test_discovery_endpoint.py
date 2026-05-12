"""Discovery endpoint tests.

We don't actually hit the network — the aggregator factory pulls
companies.yaml, and the live ATS calls happen in a background task.
For fast tests we inspect the immediate HTTP response and the persisted
task state.
"""

from __future__ import annotations

import httpx


async def test_start_discovery_returns_task_id(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.post(
        "/api/jobs/discover",
        json={
            "keywords": "engineer",
            "location": "remote",
            "remote_only": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["task_id"].startswith("disc-")
    assert body["status"] == "queued"


async def test_get_unknown_task_returns_404(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.get("/api/jobs/discover/disc-does-not-exist")
    assert response.status_code == 404
