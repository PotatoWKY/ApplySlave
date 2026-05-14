"""Lever Postings API client.

Docs: https://github.com/lever/postings-api
Public endpoint: https://api.lever.co/v0/postings/{company}?mode=json
No authentication required.
"""

from __future__ import annotations

from datetime import UTC, datetime

from applyslave.job_discovery.sources.base import (
    ATSSource,
    infer_experience_level_from_title,
)
from applyslave.shared import JobListing, JobSourceName

BASE_URL = "https://api.lever.co/v0/postings"


class LeverSource(ATSSource):
    name = JobSourceName.LEVER
    display_name = "Lever"

    async def _fetch_company_jobs(self, company: str) -> list[JobListing]:
        url = f"{BASE_URL}/{company}"
        response = await self._client.get(url, params={"mode": "json"})
        response.raise_for_status()
        payload = response.json()
        jobs: list[JobListing] = []
        for raw in payload:
            listing = self._to_listing(company, raw)
            if listing is not None:
                jobs.append(listing)
        return jobs

    def _to_listing(self, company: str, raw: dict) -> JobListing | None:
        try:
            job_id = raw["id"]
            title = raw.get("text")
            hosted_url = raw.get("hostedUrl")
            apply_url = raw.get("applyUrl") or hosted_url
            if not title or not hosted_url:
                return None
            categories = raw.get("categories") or {}
            location = categories.get("location")
            commitment = categories.get("commitment")  # "Full-time" etc
            created_at_ms = raw.get("createdAt")
            posted_at = (
                datetime.fromtimestamp(created_at_ms / 1000, tz=UTC)
                if created_at_ms
                else None
            )
            workplace_type = (raw.get("workplaceType") or "").lower()
            remote = workplace_type == "remote" or (
                bool(location) and "remote" in location.lower()
            )
            description = raw.get("descriptionPlain") or raw.get("description") or ""
            return JobListing(
                id=f"lever-{company}-{job_id}",
                source=self.name,
                company=company,
                title=title,
                location=location or commitment,
                url=hosted_url,
                apply_url=apply_url,
                description_snippet=description[:240] or None,
                posted_at=posted_at,
                remote=remote,
                employment_type=_normalize_commitment(commitment),
                experience_level=infer_experience_level_from_title(title),
            )
        except (KeyError, ValueError, TypeError):
            return None


def _normalize_commitment(commitment: str | None) -> str | None:
    """Normalize Lever's 'commitment' field to our employment_type taxonomy."""
    if not commitment:
        return None
    lower = commitment.lower()
    if "full" in lower:
        return "FULLTIME"
    if "part" in lower:
        return "PARTTIME"
    if "contract" in lower:
        return "CONTRACT"
    if "intern" in lower:
        return "INTERN"
    return None
