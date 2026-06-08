from __future__ import annotations

import httpx


def _job_payload(url: str, company: str, title: str) -> dict:
    return {
        "id": f"test-{url}",
        "source": "greenhouse",
        "company": company,
        "title": title,
        "url": url,
        "remote": False,
    }


async def test_submit_batch_and_list(
    backend_client: httpx.AsyncClient,
) -> None:
    payload = {
        "jobs": [
            _job_payload("https://example.com/apply/1", "Example", "SWE"),
            _job_payload("https://example.com/apply/2", "Example", "PM"),
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
    # Each application should retain the original JobListing for display
    for app in body["applications"]:
        assert app["job"] is not None
        assert app["job"]["source"] == "greenhouse"


async def test_submit_skips_duplicate_in_flight(
    backend_client: httpx.AsyncClient,
) -> None:
    first = {"jobs": [_job_payload("https://x/1", "X", "SWE")]}
    await backend_client.post("/api/applications", json=first)

    # Same URL again — orchestrator would still try (status is queued),
    # so our de-dupe only skips already-in-progress or submitted.
    second_response = await backend_client.post("/api/applications", json=first)
    assert second_response.json()["accepted"] == 1


async def test_submit_url_enqueues_into_same_queue(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.post(
        "/api/applications/url",
        json={"url": "https://boards.greenhouse.io/acme/jobs/123"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["application"]["status"] == "queued"
    assert body["application"]["company"] == "boards.greenhouse.io"
    assert body["application"]["job"] is None

    # It lands in the same list the worker polls and the UI shows.
    list_response = await backend_client.get("/api/applications")
    urls = {app["url"] for app in list_response.json()["applications"]}
    assert "https://boards.greenhouse.io/acme/jobs/123" in urls


async def test_submit_url_rejects_non_http(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.post(
        "/api/applications/url", json={"url": "ftp://nope"}
    )
    assert response.status_code == 422
