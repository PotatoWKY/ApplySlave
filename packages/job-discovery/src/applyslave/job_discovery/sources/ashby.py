"""Ashby Posting API client.

Public endpoint: https://api.ashbyhq.com/posting-api/job-board/{company}
No authentication required.
"""

from __future__ import annotations

from datetime import datetime

from applyslave.job_discovery.sources.base import ATSSource
from applyslave.shared import JobListing, JobSourceName

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(ATSSource):
    name = JobSourceName.ASHBY
    display_name = "Ashby"

    async def _fetch_company_jobs(self, company: str) -> list[JobListing]:
        url = f"{BASE_URL}/{company}"
        response = await self._client.get(url, params={"includeCompensation": "true"})
        response.raise_for_status()
        payload = response.json()
        jobs: list[JobListing] = []
        for raw in payload.get("jobs", []):
            listing = self._to_listing(company, raw)
            if listing is not None:
                jobs.append(listing)
        return jobs

    def _to_listing(self, company: str, raw: dict) -> JobListing | None:
        try:
            job_id = raw["id"]
            title = raw.get("title")
            job_url = raw.get("jobUrl")
            apply_url = raw.get("applyUrl") or job_url
            if not title or not job_url:
                return None
            location = raw.get("locationName")
            published_at = raw.get("publishedAt")
            posted_at = datetime.fromisoformat(published_at) if published_at else None
            remote = bool(raw.get("isRemote")) or (
                bool(location) and "remote" in location.lower()
            )
            return JobListing(
                id=f"ashby-{company}-{job_id}",
                source=self.name,
                company=company,
                title=title,
                location=location,
                url=job_url,
                apply_url=apply_url,
                posted_at=posted_at,
                remote=remote,
            )
        except (KeyError, ValueError):
            return None
