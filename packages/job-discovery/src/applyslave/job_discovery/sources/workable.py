"""Workable public API client.

Public endpoint:
  https://apply.workable.com/api/v3/accounts/{company}/jobs
  (POST with empty body; returns paginated results)

No authentication required.
"""

from __future__ import annotations

from datetime import datetime

from applyslave.job_discovery.sources.base import (
    ATSSource,
    infer_experience_level_from_title,
)
from applyslave.shared import JobListing, JobSourceName

BASE_URL = "https://apply.workable.com/api/v3/accounts"


class WorkableSource(ATSSource):
    name = JobSourceName.WORKABLE
    display_name = "Workable"

    async def _fetch_company_jobs(self, company: str) -> list[JobListing]:
        url = f"{BASE_URL}/{company}/jobs"
        # Workable requires POST for the public jobs endpoint
        response = await self._client.post(url, json={"query": "", "location": []})
        response.raise_for_status()
        payload = response.json()
        jobs: list[JobListing] = []
        for raw in payload.get("results", []):
            listing = self._to_listing(company, raw)
            if listing is not None:
                jobs.append(listing)
        return jobs

    def _to_listing(self, company: str, raw: dict) -> JobListing | None:
        try:
            shortcode = raw.get("shortcode")
            title = raw.get("title")
            if not shortcode or not title:
                return None
            location_dict = raw.get("location") or {}
            city = location_dict.get("city")
            country = location_dict.get("country")
            location = ", ".join(filter(None, [city, country])) or None
            published = raw.get("published")
            posted_at = datetime.fromisoformat(published) if published else None
            remote = bool(raw.get("remote")) or (
                bool(location) and "remote" in location.lower()
            )
            job_url = f"https://apply.workable.com/{company}/j/{shortcode}/"
            return JobListing(
                id=f"workable-{company}-{shortcode}",
                source=self.name,
                company=company,
                title=title,
                location=location,
                url=job_url,
                apply_url=f"{job_url}apply/",
                description_snippet=(raw.get("description") or "")[:240] or None,
                posted_at=posted_at,
                remote=remote,
                experience_level=infer_experience_level_from_title(title),
            )
        except (KeyError, ValueError):
            return None
