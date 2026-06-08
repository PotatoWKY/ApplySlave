"""Ashby Posting API client.

Public endpoint: https://api.ashbyhq.com/posting-api/job-board/{company}
No authentication required.
"""

from __future__ import annotations

from datetime import datetime

from hamster.job_discovery.sources.base import (
    ATSSource,
    infer_experience_level_from_title,
)
from hamster.shared import JobListing, JobSourceName

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
            employment_type_raw = raw.get("employmentType") or ""
            employment_type = _normalize_employment(employment_type_raw)

            # Ashby compensation: a list of tiers; we just look at the first
            salary_min = salary_max = salary_currency = salary_period = None
            comp_tiers = raw.get("compensationTiers") or []
            if comp_tiers and isinstance(comp_tiers, list):
                tier = comp_tiers[0]
                if isinstance(tier, dict):
                    salary_min = tier.get("minValue")
                    salary_max = tier.get("maxValue")
                    salary_currency = tier.get("currencyCode")
                    interval = (tier.get("interval") or "").lower()
                    if "year" in interval:
                        salary_period = "year"
                    elif "month" in interval:
                        salary_period = "month"
                    elif "hour" in interval:
                        salary_period = "hour"

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
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                salary_currency=salary_currency,
                salary_period=salary_period,
                employment_type=employment_type,
                experience_level=infer_experience_level_from_title(title),
            )
        except (KeyError, ValueError, TypeError):
            return None


def _normalize_employment(raw: str) -> str | None:
    if not raw:
        return None
    lower = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if "fulltime" in lower:
        return "FULLTIME"
    if "parttime" in lower:
        return "PARTTIME"
    if "contract" in lower:
        return "CONTRACT"
    if "intern" in lower:
        return "INTERN"
    return None
