"""Dump the full fill plan for a live Greenhouse form — ground truth for
'what gets filled vs left blank, and why'.

For each extracted element: its type, label, required, options, and whether
the merged plan produced an action for it (and what value). Prints the LLM's
own unmapped_fields + reasoning. No browser actions are executed beyond
extraction; nothing is submitted.

Run: .venv/bin/python scripts/diag_fill_plan.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from hamster.applicator.browser import BrowserManager, DOMExtractor
from hamster.applicator.form_filler import FormMapper
from hamster.applicator.llm import LLMClient, ModelManager
from hamster.backend.dependencies import get_data_dir, get_profile_store
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.shared import SearchQuery

logging.basicConfig(level=logging.WARNING)

REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_COMPANIES = ["anthropic", "stripe", "databricks"]


async def _find_live_job_url() -> str | None:
    for company in CANDIDATE_COMPANIES:
        source = GreenhouseSource(companies=[company])
        try:
            jobs = await source.list_jobs(SearchQuery())
        except Exception:  # noqa: BLE001
            await source.aclose()
            continue
        await source.aclose()
        if jobs:
            return str(jobs[0].apply_url or jobs[0].url)
    return None


async def main() -> int:
    profile = get_profile_store().load_profile()
    if profile is None:
        print("no saved profile")
        return 1

    url = await _find_live_job_url()
    if url is None:
        print("no live job")
        return 1
    print(f"URL: {url}\n")

    browser = BrowserManager(
        user_data_dir=REPO_ROOT / "data" / "diag_browser_profile",
        headless=True,
    )
    await browser.launch()
    page = await browser.new_page()
    await page.goto(url)
    dom = await DOMExtractor().extract(page)
    await browser.close()

    manager = ModelManager(data_dir=get_data_dir())
    llm = LLMClient(model_path=manager.model_path) if manager.is_installed() else None
    mapper = FormMapper(llm_client=llm)
    plan = await mapper.plan(dom, profile)

    action_by_selector = {a.selector: a for a in plan.actions}

    print(f"=== {len(dom.elements)} elements, {len(plan.actions)} actions, "
          f"confidence={plan.confidence:.2f} ===\n")
    for el in dom.elements:
        if el.element_type.value == "button":
            continue
        action = action_by_selector.get(el.selector)
        mark = "FILLED" if action else "BLANK "
        req = "REQ" if el.required else "opt"
        val = f" -> {action.type.value}={action.value!r}" if action else ""
        opts = f"  options={el.options}" if el.options else ""
        print(f"[{mark}] ({req}) {el.element_type.value:14} {el.label!r}{val}{opts}")

    print(f"\n=== LLM unmapped_fields ===\n{plan.unmapped_fields}")
    print(f"\n=== reasoning ===\n{plan.reasoning}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
