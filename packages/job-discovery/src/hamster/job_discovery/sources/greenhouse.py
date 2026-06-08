"""Greenhouse Job Board API client.

Docs: https://app.greenhouse.io/configure/dev_center/api_documentation
Public endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs
No authentication required.
"""

from __future__ import annotations

from datetime import datetime

from hamster.job_discovery.sources.base import (
    ATSSource,
    infer_experience_level_from_title,
)
from hamster.shared import JobListing, JobSourceName

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(ATSSource):
    name = JobSourceName.GREENHOUSE
    display_name = "Greenhouse"

    async def _fetch_company_jobs(self, company: str) -> list[JobListing]:
        url = f"{BASE_URL}/{company}/jobs"
        response = await self._client.get(url, params={"content": "true"})
        response.raise_for_status()
        payload = response.json()
        jobs: list[JobListing] = []
        for job in payload.get("jobs", []):
            listing = self._to_listing(company, job)
            if listing is not None:
                jobs.append(listing)
        return jobs

    def _to_listing(self, company: str, raw: dict) -> JobListing | None:
        try:
            job_id = str(raw["id"])
            title = raw.get("title")
            url = raw.get("absolute_url")
            if not title or not url:
                return None
            location = (raw.get("location") or {}).get("name")
            updated_at = raw.get("updated_at")
            return JobListing(
                id=f"gh-{company}-{job_id}",
                source=self.name,
                company=company,
                title=title,
                location=location,
                url=url,
                apply_url=url,
                posted_at=datetime.fromisoformat(updated_at) if updated_at else None,
                remote=_looks_remote(location),
                experience_level=infer_experience_level_from_title(title),
            )
        except (KeyError, ValueError):
            return None


def _looks_remote(location: str | None) -> bool:
    if not location:
        return False
    return "remote" in location.lower()
