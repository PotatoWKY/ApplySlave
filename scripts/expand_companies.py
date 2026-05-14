"""Build companies.yaml by harvesting public job-list repos and validating
every slug against its ATS public API.

Trust nothing. Every slug we write to yaml has been HTTP-verified at build
time. Stale entries get pruned every run because we rewrite the yaml from
scratch.

Sources:
  * SimplifyJobs / pittcsc internship & new-grad repos (active community
    maintained markdowns linking to ATS apply URLs)
  * Our own existing yaml (so previously-verified slugs survive even if
    the upstream repos drop them)
  * A small hand-curated seed list for Seattle / Bellevue heavy hitters

The repos give us hundreds of public ATS URLs. We regex-extract the slug
piece, dedupe, and probe each one's public board endpoint concurrently.

Run: python scripts/expand_companies.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import httpx
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = (
    REPO_ROOT
    / "packages"
    / "job-discovery"
    / "src"
    / "applyslave"
    / "job_discovery"
    / "companies.yaml"
)


# --- Slug harvesters ---------------------------------------------------------

# Public markdown lists. Order matters only for logging; we dedupe after.
HARVEST_SOURCES = [
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README-Off-Season.md",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/main/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2024-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2024-Internships/dev/README-Off-Season.md",
    "https://raw.githubusercontent.com/coderQuad/New-Grad-Positions-2024/main/README.md",
]


# URL → slug regexes for each ATS. We accept several known URL shapes per
# vendor because community repos format links inconsistently.
ATS_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "greenhouse": [
        re.compile(r"https?://boards\.greenhouse\.io/([a-zA-Z0-9_-]+)"),
        re.compile(r"https?://boards\.greenhouse\.io/embed/job_app\?token=[^&]+&for=([a-zA-Z0-9_-]+)"),
        re.compile(r"https?://boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)"),
        re.compile(r"https?://(?:job-boards\.greenhouse\.io)/([a-zA-Z0-9_-]+)"),
        re.compile(r"https?://boards\.eu\.greenhouse\.io/([a-zA-Z0-9_-]+)"),
    ],
    "lever": [
        re.compile(r"https?://jobs\.lever\.co/([a-zA-Z0-9_-]+)"),
        re.compile(r"https?://api\.lever\.co/v0/postings/([a-zA-Z0-9_-]+)"),
    ],
    "ashby": [
        re.compile(r"https?://jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)"),
        re.compile(r"https?://(?:www\.)?ashbyhq\.com/([a-zA-Z0-9_.-]+)/jobs"),
        re.compile(r"https?://api\.ashbyhq\.com/posting-api/job-board/([a-zA-Z0-9_.-]+)"),
    ],
    "workable": [
        re.compile(r"https?://apply\.workable\.com/([a-zA-Z0-9_-]+)/"),
        re.compile(r"https?://([a-zA-Z0-9_-]+)\.workable\.com/"),
    ],
}


# Slug fragments that are obviously not company slugs (URL fragments, common
# typos, repo-internal anchors). We reject these post-extract.
SLUG_BLOCKLIST = {
    "j", "jobs", "embed", "boards", "api", "v1", "posting-api", "search",
    "job", "post", "redirect", "login", "signin", "signup", "explore",
    "app",
}


def looks_like_slug(slug: str) -> bool:
    if not slug or slug.lower() in SLUG_BLOCKLIST:
        return False
    if len(slug) < 2 or len(slug) > 64:
        return False
    return True


def extract_from_text(text: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {ats: set() for ats in ATS_PATTERNS}
    for ats, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                slug = match.group(1).lower()
                if looks_like_slug(slug):
                    found[ats].add(slug)
    return found


# --- Probers (one per ATS) --------------------------------------------------


async def probe_greenhouse(client: httpx.AsyncClient, slug: str) -> bool:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        response = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload.get("jobs"), list)


async def probe_lever(client: httpx.AsyncClient, slug: str) -> bool:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        response = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, list)


async def probe_ashby(client: httpx.AsyncClient, slug: str) -> bool:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        response = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload.get("jobs"), list)


async def probe_workable(client: httpx.AsyncClient, slug: str) -> bool:
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    try:
        response = await client.post(
            url,
            json={"query": "", "location": []},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload.get("results"), list)


PROBERS = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
    "workable": probe_workable,
}


# --- Pipeline ---------------------------------------------------------------


async def harvest_slugs(client: httpx.AsyncClient) -> dict[str, set[str]]:
    aggregate: dict[str, set[str]] = {ats: set() for ats in ATS_PATTERNS}
    for url in HARVEST_SOURCES:
        try:
            response = await client.get(url, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            print(f"  [warn] could not fetch {url}: {error}")
            continue
        found = extract_from_text(response.text)
        for ats, slugs in found.items():
            aggregate[ats].update(slugs)
        total = sum(len(slugs) for slugs in found.values())
        print(f"  {url.split('/')[-1]:<35} +{total} slugs")
    return aggregate


def merge_existing(harvested: dict[str, set[str]]) -> dict[str, set[str]]:
    """Union the harvested set with whatever is already in companies.yaml.

    Treats the existing yaml as a trusted seed: yes, we'll re-probe it (so
    stale entries fall out), but we don't lose hand-curated slugs that
    weren't in any harvest source.
    """
    if not YAML_PATH.exists():
        return harvested
    existing = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    merged = {ats: set(slugs) for ats, slugs in harvested.items()}
    for ats, slugs in existing.items():
        if ats in merged and isinstance(slugs, list):
            merged[ats].update(slug.lower() for slug in slugs)
    return merged


async def verify_pool(
    client: httpx.AsyncClient, ats: str, candidates: set[str]
) -> tuple[list[str], list[str]]:
    probe = PROBERS[ats]
    semaphore = asyncio.Semaphore(40)

    async def _check(slug: str) -> tuple[str, bool]:
        async with semaphore:
            ok = await probe(client, slug)
        return slug, ok

    results = await asyncio.gather(*(_check(slug) for slug in candidates))
    good = sorted({slug for slug, ok in results if ok})
    bad = sorted({slug for slug, ok in results if not ok})
    return good, bad


def write_yaml(verified: dict[str, list[str]]) -> None:
    ordered = {
        ats: verified.get(ats, [])
        for ats in ("greenhouse", "lever", "ashby", "workable")
    }
    header = (
        "# Seed list of companies hiring publicly through each ATS.\n"
        "# Auto-verified by scripts/expand_companies.py — every slug here\n"
        "# responded 200 with a jobs array at build time.\n"
        "#\n"
        "# Company slug = the path segment in the company's career page URL\n"
        "# (e.g. boards.greenhouse.io/stripe → slug is \"stripe\").\n\n"
    )
    body = yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False)
    YAML_PATH.write_text(header + body)


async def main() -> int:
    async with httpx.AsyncClient(
        headers={"User-Agent": "applyslave-expand/1.1"},
        follow_redirects=True,
    ) as client:
        print("Harvesting slugs from public sources…")
        harvested = await harvest_slugs(client)
        candidates = merge_existing(harvested)
        for ats, slugs in candidates.items():
            print(f"  {ats:<11} {len(slugs)} candidates after merge")

        verified: dict[str, list[str]] = {}
        rejected: dict[str, list[str]] = {}
        for ats in ("greenhouse", "lever", "ashby", "workable"):
            print(f"\n[{ats}] probing {len(candidates[ats])} slugs concurrently…")
            good, bad = await verify_pool(client, ats, candidates[ats])
            verified[ats] = good
            rejected[ats] = bad
            print(f"[{ats}]   {len(good)} verified, {len(bad)} rejected")

    total = sum(len(v) for v in verified.values())
    write_yaml(verified)
    print(f"\nWrote {YAML_PATH.relative_to(REPO_ROOT)}: {total} verified slugs")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
