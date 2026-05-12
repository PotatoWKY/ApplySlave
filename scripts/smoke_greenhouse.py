"""Live smoke test: hit Greenhouse's public API for one real company.

Not a pytest — just a sanity check against the real internet.
Run:  uv run python scripts/smoke_greenhouse.py
"""

from __future__ import annotations

import asyncio

from applyslave.job_discovery import GreenhouseSource
from applyslave.shared import SearchQuery


async def main() -> None:
    async with GreenhouseSource(companies=["figma"]) as source:
        jobs = await source.list_jobs(SearchQuery(keywords="engineer", max_results=5))
    print(f"Fetched {len(jobs)} engineering jobs from Figma")
    for job in jobs[:3]:
        print(f"  - {job.title} @ {job.company} ({job.location})")


if __name__ == "__main__":
    asyncio.run(main())
