"""JSearch (RapidAPI) source — Google Jobs aggregation.

Unlike the ATS sources which fan out to individual company boards, JSearch
is a search engine: you give it a query string and it returns results from
across all job boards (LinkedIn, Indeed, Glassdoor, company career pages,
Workday, iCIMS, etc).

This gives us coverage of non-tech companies and ATS platforms that don't
have public APIs (Workday, Taleo, SuccessFactors).

Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
Free tier: 200 requests/month.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from hamster.shared import JobListing, JobSourceName, SearchQuery

logger = logging.getLogger(__name__)

BASE_URL = "https://jsearch.p.rapidapi.com/search-v2"


class JSearchSource:
    """Job search via JSearch (Google Jobs aggregation)."""

    name = JobSourceName.JSEARCH
    display_name = "JSearch"

    def __init__(self, *, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "JSearchSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def list_jobs(self, query: SearchQuery) -> list[JobListing]:
        """Search JSearch with the user's query and return normalized results."""
        search_query = _build_query_string(query)
        if not search_query:
            return []

        params = {
            "query": search_query,
            "num_pages": "1",
            "country": "us",
            "date_posted": "week",
        }
        if query.remote_only:
            params["remote_jobs_only"] = "true"

        headers = {
            "x-rapidapi-host": "jsearch.p.rapidapi.com",
            "x-rapidapi-key": self._api_key,
        }

        try:
            response = await self._client.get(BASE_URL, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("JSearch request failed: %s", error)
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("JSearch returned non-JSON response")
            return []

        raw_jobs = _extract_jobs(payload)
        listings = []
        for raw in raw_jobs:
            listing = _to_listing(raw)
            if listing is not None:
                if _passes_exclusion(listing, query):
                    listings.append(listing)

        return listings[: query.max_results]


def _build_query_string(query: SearchQuery) -> str:
    """Build a natural-language search string from the structured query."""
    parts = []
    if query.keywords:
        parts.append(query.keywords)
    if query.location:
        parts.append(f"in {query.location}")
    return " ".join(parts)


def _extract_jobs(payload: dict) -> list[dict]:
    """Handle both v1 and v2 response formats."""
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("jobs", [])
    return []


def _to_listing(raw: dict) -> JobListing | None:
    """Convert a JSearch job object to our normalized JobListing."""
    try:
        job_id = raw.get("job_id", "")
        title = raw.get("job_title")
        company = raw.get("employer_name")
        apply_link = (
            raw.get("job_apply_link")
            or raw.get("job_google_link")
            or ""
        )
        if not title or not company or not apply_link:
            return None

        city = raw.get("job_city") or ""
        state = raw.get("job_state") or ""
        country = raw.get("job_country") or ""
        location_parts = [part for part in (city, state, country) if part]
        location = ", ".join(location_parts) or None

        is_remote = bool(raw.get("job_is_remote"))
        posted_at_str = raw.get("job_posted_at_datetime_utc")
        posted_at = None
        if posted_at_str:
            try:
                posted_at = datetime.fromisoformat(
                    posted_at_str.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        description = raw.get("job_description") or ""

        # Salary parsing
        salary_min = raw.get("job_min_salary")
        salary_max = raw.get("job_max_salary")
        salary_currency = raw.get("job_salary_currency")
        salary_period_raw = raw.get("job_salary_period") or ""
        salary_period = salary_period_raw.lower() if salary_period_raw else None

        # Employment type and experience level
        employment_type = raw.get("job_employment_type") or None
        experience_level = _infer_experience_level(
            title, raw.get("job_required_experience")
        )

        return JobListing(
            id=f"jsearch-{job_id[:32]}" if job_id else f"jsearch-{hash(apply_link)}",
            source=JobSourceName.JSEARCH,
            company=company,
            title=title,
            location=location,
            url=apply_link,
            apply_url=apply_link,
            description_snippet=description[:240] if description else None,
            posted_at=posted_at,
            remote=is_remote,
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency=salary_currency,
            salary_period=salary_period,
            employment_type=employment_type,
            experience_level=experience_level,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _infer_experience_level(title: str, required: dict | None) -> str | None:
    """Best-effort extraction from title keywords + required years."""
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("intern", "internship")):
        return "intern"
    if any(kw in title_lower for kw in ("staff", "principal", "director", "vp ")):
        return "lead"
    if any(kw in title_lower for kw in ("senior", "sr.", "sr ", "lead")):
        return "senior"
    if any(kw in title_lower for kw in ("junior", "jr.", "jr ", "entry", "associate")):
        return "entry"

    if required and isinstance(required, dict):
        months = required.get("required_experience_in_months")
        if isinstance(months, (int, float)):
            years = months / 12
            if years < 2:
                return "entry"
            if years < 5:
                return "mid"
            if years < 8:
                return "senior"
            return "lead"
    return None


def _passes_exclusion(listing: JobListing, query: SearchQuery) -> bool:
    """Check exclusion list and level filter."""
    exclude_lower = {company.lower() for company in query.exclude_companies}
    if listing.company.lower() in exclude_lower:
        return False
    allowed_levels = {level.lower() for level in query.experience_levels}
    if allowed_levels and listing.experience_level:
        if listing.experience_level not in allowed_levels:
            return False
    return True
