"""Unit tests for each ATS source using httpx MockTransport.

These tests never hit the network — they substitute httpx's transport with
one that responds to specific URLs with fixture payloads. This gives us the
coverage of "this source can actually parse real-looking ATS JSON" without
needing live endpoints.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from applyslave.job_discovery import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    WorkableSource,
)
from applyslave.shared import JobSourceName, SearchQuery


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, follow_redirects=True)


# --- Greenhouse -----------------------------------------------------------


GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 1001,
            "title": "Senior Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/teststripe/jobs/1001",
            "updated_at": "2026-02-10T10:00:00+00:00",
            "location": {"name": "San Francisco, CA"},
        },
        {
            "id": 1002,
            "title": "Product Manager",
            "absolute_url": "https://boards.greenhouse.io/teststripe/jobs/1002",
            "updated_at": "2026-02-11T10:00:00+00:00",
            "location": {"name": "Remote, Americas"},
        },
    ]
}


async def test_greenhouse_source_parses_listings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "boards-api.greenhouse.io" in str(request.url)
        return httpx.Response(200, json=GREENHOUSE_PAYLOAD)

    async with _mock_client(handler) as client:
        source = GreenhouseSource(companies=["teststripe"], client=client)
        jobs = await source.list_jobs(SearchQuery())

    assert len(jobs) == 2
    assert jobs[0].source is JobSourceName.GREENHOUSE
    assert jobs[0].company == "teststripe"
    assert any("Remote" in (job.location or "") for job in jobs)
    assert any(job.remote for job in jobs)


# --- Lever ----------------------------------------------------------------


LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/testnetflix/abc-123",
        "applyUrl": "https://jobs.lever.co/testnetflix/abc-123/apply",
        "createdAt": 1_740_000_000_000,
        "categories": {"location": "Remote - US", "commitment": "Full-time"},
        "workplaceType": "remote",
        "descriptionPlain": "Build great backend systems.",
    }
]


async def test_lever_source_parses_listings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.lever.co" in str(request.url)
        return httpx.Response(200, json=LEVER_PAYLOAD)

    async with _mock_client(handler) as client:
        source = LeverSource(companies=["testnetflix"], client=client)
        jobs = await source.list_jobs(SearchQuery())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Backend Engineer"
    assert job.remote is True
    assert job.apply_url is not None
    assert "apply" in str(job.apply_url)


# --- Ashby ----------------------------------------------------------------


ASHBY_PAYLOAD = {
    "jobs": [
        {
            "id": "a11-22-33",
            "title": "Frontend Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/testlinear/a11-22-33",
            "applyUrl": "https://jobs.ashbyhq.com/testlinear/a11-22-33/application",
            "locationName": "Remote — Americas",
            "isRemote": True,
            "publishedAt": "2026-02-12T00:00:00+00:00",
        }
    ]
}


async def test_ashby_source_parses_listings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.ashbyhq.com" in str(request.url)
        return httpx.Response(200, json=ASHBY_PAYLOAD)

    async with _mock_client(handler) as client:
        source = AshbySource(companies=["testlinear"], client=client)
        jobs = await source.list_jobs(SearchQuery())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Frontend Engineer"
    assert job.remote is True


# --- Workable -------------------------------------------------------------


WORKABLE_PAYLOAD = {
    "results": [
        {
            "shortcode": "XYZ789",
            "title": "Customer Success Engineer",
            "location": {"city": "Berlin", "country": "Germany"},
            "published": "2026-02-09T08:00:00+00:00",
            "remote": False,
            "description": "Talk to customers about engineering things.",
        }
    ],
    "total": 1,
}


async def test_workable_source_parses_listings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "apply.workable.com" in str(request.url)
        assert request.method == "POST"
        return httpx.Response(200, json=WORKABLE_PAYLOAD)

    async with _mock_client(handler) as client:
        source = WorkableSource(companies=["testaircall"], client=client)
        jobs = await source.list_jobs(SearchQuery())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Customer Success Engineer"
    assert str(job.url).startswith("https://apply.workable.com/testaircall/j/XYZ789")


# --- Failure isolation ----------------------------------------------------


async def test_source_tolerates_per_company_failure() -> None:
    """If one company's endpoint errors, others still yield jobs."""
    good_payload = GREENHOUSE_PAYLOAD

    def handler(request: httpx.Request) -> httpx.Response:
        if "goodco" in str(request.url):
            return httpx.Response(200, json=good_payload)
        return httpx.Response(404)

    async with _mock_client(handler) as client:
        source = GreenhouseSource(
            companies=["goodco", "badco"], client=client
        )
        jobs = await source.list_jobs(SearchQuery())

    assert len(jobs) == 2
    assert all(job.company == "goodco" for job in jobs)


pytestmark = pytest.mark.asyncio
