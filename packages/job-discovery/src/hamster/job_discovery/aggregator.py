"""Run multiple JobSources in parallel and merge their results.

Dedup happens on normalized (company, title) pair to avoid the common case
where the same role is posted under a parent + subsidiary ATS slug.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from hamster.shared import JobListing, JobSource, SearchQuery

logger = logging.getLogger(__name__)


class DiscoveryAggregator:
    """Orchestrates fan-out across multiple JobSource implementations."""

    def __init__(self, sources: Iterable[JobSource]) -> None:
        self._sources = list(sources)

    async def discover(self, query: SearchQuery) -> list[JobListing]:
        tasks = [self._safe_list(source, query) for source in self._sources]
        results = await asyncio.gather(*tasks)
        flat: list[JobListing] = []
        for group in results:
            flat.extend(group)
        return _dedupe(flat)

    async def _safe_list(
        self, source: JobSource, query: SearchQuery
    ) -> list[JobListing]:
        try:
            return await source.list_jobs(query)
        except Exception as error:  # noqa: BLE001 - best-effort boundary
            logger.warning("Source %s failed: %s", source.name, error)
            return []


def _dedupe(jobs: list[JobListing]) -> list[JobListing]:
    seen: set[tuple[str, str]] = set()
    deduped: list[JobListing] = []
    for job in jobs:
        key = (job.company.lower(), job.title.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped
