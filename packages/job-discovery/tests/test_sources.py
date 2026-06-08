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
from hamster.job_discovery import (
    AshbySource,
    GreenhouseSource,
    JSearchSource,
    LeverSource,
    WorkableSource,
)
from hamster.shared import JobSourceName, SearchQuery


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


# --- JSearch --------------------------------------------------------------


# v2 format: data is a dict with a "jobs" list.
JSEARCH_V2_PAYLOAD = {
    "data": {
        "jobs": [
            {
                "job_id": "jsearch-id-001",
                "job_title": "Senior Backend Engineer",
                "employer_name": "TestCorp",
                "job_apply_link": "https://testcorp.com/jobs/001/apply",
                "job_city": "Seattle",
                "job_state": "WA",
                "job_country": "US",
                "job_is_remote": False,
                "job_posted_at_datetime_utc": "2026-02-10T10:00:00Z",
                "job_description": "Build backend systems at scale.",
                "job_min_salary": 150000,
                "job_max_salary": 200000,
                "job_salary_currency": "USD",
                "job_salary_period": "YEAR",
                "job_employment_type": "FULLTIME",
            }
        ]
    }
}


async def test_jsearch_source_parses_listings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "jsearch.p.rapidapi.com" in str(request.url)
        # The API key must travel as the RapidAPI header on every request.
        assert request.headers["x-rapidapi-key"] == "test-key"
        return httpx.Response(200, json=JSEARCH_V2_PAYLOAD)

    async with _mock_client(handler) as client:
        source = JSearchSource(api_key="test-key", client=client)
        jobs = await source.list_jobs(SearchQuery(keywords="backend engineer"))

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source is JobSourceName.JSEARCH
    assert job.title == "Senior Backend Engineer"
    assert job.company == "TestCorp"
    assert job.location == "Seattle, WA, US"
    assert job.salary_min == 150000
    assert job.salary_max == 200000
    assert job.salary_currency == "USD"
    assert job.salary_period == "year"
    assert job.experience_level == "senior"  # inferred from "Senior" in title


async def test_jsearch_source_parses_v1_list_format() -> None:
    """v1 format returns ``data`` as a bare list rather than ``data.jobs``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": JSEARCH_V2_PAYLOAD["data"]["jobs"]})

    async with _mock_client(handler) as client:
        source = JSearchSource(api_key="test-key", client=client)
        jobs = await source.list_jobs(SearchQuery(keywords="backend"))

    assert len(jobs) == 1
    assert jobs[0].company == "TestCorp"


async def test_jsearch_source_skips_jobs_missing_required_fields() -> None:
    """A job with no apply link / title / company is dropped, not crashed on."""
    payload = {
        "data": [
            {"job_id": "x", "job_title": "No Company Or Link"},
            JSEARCH_V2_PAYLOAD["data"]["jobs"][0],
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _mock_client(handler) as client:
        source = JSearchSource(api_key="test-key", client=client)
        jobs = await source.list_jobs(SearchQuery(keywords="engineer"))

    assert len(jobs) == 1
    assert jobs[0].company == "TestCorp"


async def test_jsearch_source_returns_empty_on_blank_query() -> None:
    """No keywords + no location means no search string, so no request fires."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=JSEARCH_V2_PAYLOAD)

    async with _mock_client(handler) as client:
        source = JSearchSource(api_key="test-key", client=client)
        jobs = await source.list_jobs(SearchQuery())

    assert jobs == []
    assert calls == 0


async def test_jsearch_source_returns_empty_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    async with _mock_client(handler) as client:
        source = JSearchSource(api_key="test-key", client=client)
        jobs = await source.list_jobs(SearchQuery(keywords="engineer"))

    assert jobs == []


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
