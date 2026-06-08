from __future__ import annotations

from datetime import UTC, datetime

from hamster.job_discovery import apply_query_filters
from hamster.shared import JobListing, JobSourceName, SearchQuery


def _listing(**overrides) -> JobListing:
    base = dict(
        id="test-1",
        source=JobSourceName.GREENHOUSE,
        company="TestCo",
        title="Software Engineer",
        location="San Francisco",
        url="https://example.com/jobs/1",
        remote=False,
    )
    base.update(overrides)
    return JobListing(**base)  # type: ignore[arg-type]


def test_keyword_filter_matches_title() -> None:
    jobs = [
        _listing(title="Software Engineer"),
        _listing(title="Product Manager", id="test-2"),
    ]
    result = apply_query_filters(jobs, SearchQuery(keywords="engineer"))
    assert len(result) == 1
    assert result[0].title == "Software Engineer"


def test_keyword_filter_matches_description() -> None:
    jobs = [
        _listing(
            title="Software Engineer",
            description_snippet="Build APIs with python.",
        ),
        _listing(
            id="test-2",
            title="Product Manager",
            description_snippet="Coordinate roadmap.",
        ),
    ]
    result = apply_query_filters(jobs, SearchQuery(keywords="python"))
    assert len(result) == 1
    assert result[0].title == "Software Engineer"


def test_exclude_companies_case_insensitive() -> None:
    jobs = [
        _listing(company="Oracle"),
        _listing(id="test-2", company="Stripe"),
    ]
    result = apply_query_filters(
        jobs, SearchQuery(exclude_companies=["ORACLE"])
    )
    assert [job.company for job in result] == ["Stripe"]


def test_remote_only_accepts_remote_flag() -> None:
    jobs = [
        _listing(location="New York", remote=False),
        _listing(id="test-2", location="Remote", remote=True),
    ]
    result = apply_query_filters(jobs, SearchQuery(remote_only=True))
    assert len(result) == 1
    assert result[0].remote is True


def test_max_results_caps_output() -> None:
    jobs = [_listing(id=f"test-{i}") for i in range(5)]
    result = apply_query_filters(jobs, SearchQuery(max_results=2))
    assert len(result) == 2


def test_sorted_by_posted_at_desc_when_present() -> None:
    jobs = [
        _listing(id="a", posted_at=datetime(2026, 1, 1, tzinfo=UTC)),
        _listing(id="b", posted_at=datetime(2026, 3, 1, tzinfo=UTC)),
        _listing(id="c", posted_at=datetime(2026, 2, 1, tzinfo=UTC)),
    ]
    result = apply_query_filters(jobs, SearchQuery())
    assert [job.id for job in result] == ["b", "c", "a"]
