"""Aggregator and factory tests."""

from __future__ import annotations

from hamster.job_discovery import DiscoveryAggregator, load_default_companies
from hamster.shared import JobListing, JobSourceName, SearchQuery


class _StaticSource:
    def __init__(self, name: JobSourceName, jobs: list[JobListing]) -> None:
        self.name = name
        self._jobs = jobs

    async def list_jobs(self, query: SearchQuery) -> list[JobListing]:
        return list(self._jobs)


def _listing(**overrides) -> JobListing:
    base = dict(
        id="x-1",
        source=JobSourceName.GREENHOUSE,
        company="TestCo",
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )
    base.update(overrides)
    return JobListing(**base)  # type: ignore[arg-type]


async def test_aggregator_dedupes_on_company_title() -> None:
    a_source = _StaticSource(
        JobSourceName.GREENHOUSE,
        [_listing(id="a-1", company="Stripe", title="Engineer")],
    )
    b_source = _StaticSource(
        JobSourceName.LEVER,
        [
            _listing(id="b-1", company="stripe", title="engineer"),
            _listing(id="b-2", company="Figma", title="Designer"),
        ],
    )
    aggregator = DiscoveryAggregator([a_source, b_source])
    jobs = await aggregator.discover(SearchQuery())
    assert len(jobs) == 2
    companies = {job.company.lower() for job in jobs}
    assert companies == {"stripe", "figma"}


async def test_aggregator_tolerates_failing_source() -> None:
    class _Broken:
        name = JobSourceName.ASHBY

        async def list_jobs(self, query: SearchQuery) -> list[JobListing]:
            raise RuntimeError("network down")

    good = _StaticSource(
        JobSourceName.GREENHOUSE, [_listing(company="GoodCo")]
    )
    aggregator = DiscoveryAggregator([_Broken(), good])
    jobs = await aggregator.discover(SearchQuery())
    assert len(jobs) == 1
    assert jobs[0].company == "GoodCo"


def test_default_companies_yaml_loads() -> None:
    companies = load_default_companies()
    assert "greenhouse" in companies
    assert "lever" in companies
    assert "ashby" in companies
    assert "workable" in companies
    assert len(companies["greenhouse"]) > 0
