"""Common HTTP helpers for ATS clients.

Every ATS source we support exposes a public, no-auth JSON endpoint. This
module centralizes the tiny amount of infrastructure they share (httpx client
creation, retry, and a helper for filtering locally after fetch) so each
concrete source stays focused on the ATS-specific schema.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable

import httpx

from hamster.shared import JobListing, JobSourceName, SearchQuery

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def infer_experience_level_from_title(title: str) -> str | None:
    """Best-effort extraction of seniority level from a job title.

    Returns one of: 'intern', 'entry', 'mid', 'senior', 'lead', or None.
    Used by ATS sources where the API doesn't return level explicitly.
    """
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("intern", "internship")):
        return "intern"
    if any(kw in title_lower for kw in ("staff ", "principal ", "director ", "vp ", " vp")):
        return "lead"
    if any(kw in title_lower for kw in ("senior", "sr.", "sr ", "lead ", " lead")):
        return "senior"
    if any(kw in title_lower for kw in ("junior", "jr.", "jr ", "entry", "associate", " i ", " ii")):
        return "entry"
    return None


class ATSSource(ABC):
    """Base class for all public-API-backed ATS sources."""

    name: JobSourceName
    display_name: str

    def __init__(
        self,
        *,
        companies: Iterable[str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._companies = list(companies)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": "hamster/0.1"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ATSSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # --- Public API -----------------------------------------------------

    async def list_jobs(self, query: SearchQuery) -> list[JobListing]:
        """Fetch all jobs across configured companies then filter locally.

        ATS public APIs generally don't support server-side keyword search, so
        we fan out, collect, then filter.
        """
        tasks = [self._fetch_company_jobs(company) for company in self._companies]
        results: list[list[JobListing]] = []
        for coro in asyncio.as_completed(tasks):
            try:
                jobs = await coro
                results.append(jobs)
            except httpx.HTTPError as error:
                logger.warning("%s fetch failed: %s", self.display_name, error)
        flat = [job for group in results for job in group]
        return apply_query_filters(flat, query)

    # --- Subclass hooks -------------------------------------------------

    @abstractmethod
    async def _fetch_company_jobs(self, company: str) -> list[JobListing]:
        """Fetch jobs for a single company slug. Raises httpx errors on failure."""


# --- Filtering shared across sources ----------------------------------------


def apply_query_filters(
    jobs: list[JobListing], query: SearchQuery
) -> list[JobListing]:
    """Pure function: apply keyword / location / exclusion filters in memory."""
    needle = query.keywords.lower().strip()
    location_needle = query.location.lower().strip()
    exclude_lower = {c.lower() for c in query.exclude_companies}
    allowed_levels = {level.lower() for level in query.experience_levels}

    filtered: list[JobListing] = []
    for job in jobs:
        if needle and needle not in job.title.lower():
            # Also try description as fallback
            if not job.description_snippet or needle not in job.description_snippet.lower():
                continue
        if location_needle:
            location_str = (job.location or "").lower()
            if location_needle not in location_str:
                # Allow "remote" as a special case
                if not (query.remote_only and job.remote):
                    continue
        if query.remote_only and not job.remote:
            # Some ATS don't flag `remote`, so fall back to location text
            if "remote" not in (job.location or "").lower():
                continue
        if job.company.lower() in exclude_lower:
            continue
        # Level filter: if user specified levels, drop jobs whose inferred
        # level is set AND not in the allow-list. Jobs with no inferred level
        # are kept (we'd rather show a maybe-relevant job than miss it).
        if allowed_levels and job.experience_level:
            if job.experience_level not in allowed_levels:
                continue
        filtered.append(job)

    filtered.sort(key=lambda job: (job.posted_at or 0, job.company), reverse=True)
    return filtered[: query.max_results]
