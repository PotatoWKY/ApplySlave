"""Expand companies.yaml by probing public ATS APIs for known candidates.

We never trust a slug until the ATS's public board endpoint returns 2xx with
at least one job (or an empty array, which is still a valid board). Keeps the
yaml honest: every entry in it actually works.

Candidate pool is intentionally large — it includes:
  * Seattle / Bellevue-area tech (primary target for the user)
  * General US tech (SaaS, fintech, AI, consumer, dev tools)
  * Remote-first companies

Run: python scripts/expand_companies.py
"""

from __future__ import annotations

import asyncio
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


# --- Candidate pool ---------------------------------------------------------
#
# Slugs are lowercased, no spaces. When a company is known under multiple
# slugs (eg. parent + subsidiary), include both; the verifier will keep
# whichever answer. Never include a slug we're not at least 70% confident
# about — verifier will prune the rest.


GREENHOUSE_CANDIDATES = [
    # Existing
    "airbnb", "stripe", "figma", "databricks", "anthropic", "dropbox",
    "doordash", "instacart", "coinbase", "opendoor", "robinhood", "plaid",
    "affirm", "elastic", "confluent",
    # Seattle / Bellevue area
    "smartsheet", "zillow", "expedia", "redfin", "outreach", "remitly",
    "convoy", "auth0", "rover", "segment", "tableau", "pointinside",
    "highspot", "offerup", "icertis", "extrahop", "picsart", "qumulo",
    "apptio", "pushpay", "mavenlink", "accolade", "bsquare",
    # Big SV tech on greenhouse
    "pinterest", "reddit", "lyft", "twitch", "gitlab", "hashicorp",
    "cloudflare", "airtable", "asana", "notion", "discord", "retool",
    "vanta", "ramp", "mercury", "mixpanel", "amplitude", "segment",
    "postman", "twilio", "intercom", "zendesk", "fastly", "datadog",
    "dropboxsign", "wealthfront", "chime", "kraken", "gusto", "carta",
    "klaviyo", "toast", "samsara", "stord", "mercari", "nextdoor",
    "grammarly", "quora", "duolingo", "masterclass", "coursera",
    "unity3d", "unity", "epicgames", "niantic", "roblox",
    # AI
    "openai", "huggingface", "runwayml", "mistralai", "scale",
    "perplexityai", "inflection", "adept", "cohere", "scaleai",
    # Fintech
    "betterment", "brex", "ramp", "atomicfinancial", "acorns",
    "public", "moneylion", "sofi", "marqeta", "block", "square",
    # Dev tools / infra
    "stytch", "workos", "knockdotcom", "render", "fly", "doppler",
    "railway", "warpdotdev", "bun", "sentry", "circleci", "snyk",
    "tailscale", "temporal", "terraform", "pulumi",
    # Consumer
    "spotifyshop", "etsy", "doordashmerchant", "postmates",
    # Workplace / collaboration
    "box", "atlassian", "miro", "loom",
    # Gaming / creative
    "unity",
    # Media
    "medium", "substack", "reddit",
    # Extras verified via probe
    "hellofresh", "waymo", "mongodb", "earnin", "okta",
]


LEVER_CANDIDATES = [
    # Existing
    "netflix", "ramp", "brex", "mixpanel", "alchemy", "spotify",
    "shopify", "palantir", "fivetran", "ironclad",
    # SV tech
    "quora", "discord", "faire", "opendoor",
    "github", "hopin", "jumpcloud", "tripadvisor", "attentive",
    "lob", "stockx", "vectra", "sigmacomputing", "anduril",
    "signifyhealth", "circle", "checkr", "addepar", "webflow",
    "cresta", "matterport", "ironclad",
    # Seattle
    "sessionai",
    # Fintech / crypto
    "kraken", "anchorage", "figure", "ondeck", "payjoy",
    # Dev tools
    "growthbook", "launchdarkly", "segmenthq", "vanta", "mixpanel",
    "vercel",
    # Health
    "oscar", "cedar", "olive", "gethealthy",
    # Media / consumer
    "stashinvest", "betterment", "thrivemarket",
]


ASHBY_CANDIDATES = [
    # Existing
    "posthog", "supabase", "vercel", "linear", "replicate", "hex", "clerk",
    # Known Ashby users
    "openai", "ramp", "hexops", "mux", "neondatabase", "prisma",
    "railway", "trigger", "turso", "resend", "supabaseinc",
    "incident", "monite", "metabase", "readme", "modal",
    "crusoe", "weaviate", "stytch", "inflectionai",
    "raycast", "contrary", "warp", "paragraph", "sentry",
    "linearapp", "betterup", "poolside", "anthropic", "togetherai",
    "groqinc", "fal", "langchain", "arizeai", "wandb",
    "crewai", "lovable", "cursor", "codeium", "windsurf",
    "baseten", "patternai", "chroma", "pineconeinc",
]


WORKABLE_CANDIDATES = [
    # Existing
    "aircall", "stampli", "huspy",
    "rippling", "loom", "typeform", "deel",
    # SMB / EU
    "hotjar", "remotecom", "pipedrive", "revolut",
    "personio", "plaid", "mindtickle", "trustpilot",
    "bolt", "algolia", "contentful", "yousign", "amplemarket",
    "productboard", "wise", "tide", "bunq", "hostelworld",
    "gitpod", "teleport", "mews", "lokalise", "spendesk",
    "agorapulse", "buffer", "sumup",
]


# Dedup before probing
def _dedup(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        low = item.lower().strip()
        if low and low not in seen:
            seen.add(low)
            out.append(low)
    return out


# --- Probers ---------------------------------------------------------------


async def probe_greenhouse(client: httpx.AsyncClient, slug: str) -> bool:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        response = await client.get(url, timeout=8.0)
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
        response = await client.get(url, timeout=8.0)
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
        response = await client.get(url, timeout=8.0)
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
            timeout=8.0,
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


# --- Main ---

async def verify_batch(
    client: httpx.AsyncClient,
    ats: str,
    candidates: list[str],
) -> tuple[list[str], list[str]]:
    probe = PROBERS[ats]
    semaphore = asyncio.Semaphore(20)

    async def _check(slug: str) -> tuple[str, bool]:
        async with semaphore:
            ok = await probe(client, slug)
        return slug, ok

    results = await asyncio.gather(*(_check(c) for c in candidates))
    good = sorted({slug for slug, ok in results if ok})
    bad = sorted({slug for slug, ok in results if not ok})
    return good, bad


async def main() -> int:
    pools = {
        "greenhouse": _dedup(GREENHOUSE_CANDIDATES),
        "lever": _dedup(LEVER_CANDIDATES),
        "ashby": _dedup(ASHBY_CANDIDATES),
        "workable": _dedup(WORKABLE_CANDIDATES),
    }

    verified: dict[str, list[str]] = {}
    rejected: dict[str, list[str]] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": "applyslave-expand/1.0"},
        follow_redirects=True,
    ) as client:
        for ats, candidates in pools.items():
            print(f"[{ats}] probing {len(candidates)} candidates…")
            good, bad = await verify_batch(client, ats, candidates)
            verified[ats] = good
            rejected[ats] = bad
            print(f"[{ats}]   {len(good)} verified, {len(bad)} rejected")

    total = sum(len(v) for v in verified.values())
    print(f"\nTotal verified slugs: {total}")

    _write_yaml(verified)

    print(f"\nWrote {YAML_PATH.relative_to(REPO_ROOT)}")
    print("\nRejected slugs (for reference):")
    for ats, slugs in rejected.items():
        for slug in slugs:
            print(f"  {ats:<11} {slug}")
    return 0


def _write_yaml(verified: dict[str, list[str]]) -> None:
    ordered = {ats: verified.get(ats, []) for ats in ("greenhouse", "lever", "ashby", "workable")}
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


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
