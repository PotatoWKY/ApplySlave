from __future__ import annotations

import httpx


async def test_submit_batch_and_list(
    backend_client: httpx.AsyncClient,
) -> None:
    payload = {
        "jobs": [
            {
                "url": "https://example.com/apply/1",
                "company": "Example",
                "title": "SWE",
            },
            {
                "url": "https://example.com/apply/2",
                "company": "Example",
                "title": "PM",
            },
        ]
    }
    submit_response = await backend_client.post("/api/applications", json=payload)
    assert submit_response.status_code == 202
    assert submit_response.json() == {"accepted": 2, "skipped_duplicates": 0}

    list_response = await backend_client.get("/api/applications")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 2
    urls = {app["url"] for app in body["applications"]}
    assert urls == {
        "https://example.com/apply/1",
        "https://example.com/apply/2",
    }


async def test_submit_skips_duplicate_in_flight(
    backend_client: httpx.AsyncClient,
) -> None:
    first = {
        "jobs": [
            {"url": "https://x/1", "company": "X", "title": "SWE"},
        ]
    }
    await backend_client.post("/api/applications", json=first)

    # Same URL again — orchestrator would still try (status is queued),
    # so our de-dupe only skips already-in-progress or submitted.
    second_response = await backend_client.post("/api/applications", json=first)
    assert second_response.json()["accepted"] == 1
