"""Measure combobox option-harvest reliability vs. a hydration wait.

Hypothesis: the extractor clicks react-select comboboxes before React has
hydrated (extract() only waits for domcontentloaded), so the click is a no-op
and the option menu never renders -> 3s timeout -> empty options -> the LLM
later invents an out-of-range value.

This runs the SAME open-read-close harvest the extractor uses, under three
conditions, N times each, and reports how many comboboxes yield options:
  A) no wait (current behavior)
  B) wait_for_load_state('networkidle')
  C) networkidle + one retry on the open

Nothing is submitted. Run: .venv/bin/python scripts/diag_harvest_race.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from hamster.applicator.browser import BrowserManager
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.shared import SearchQuery

REPO_ROOT = Path(__file__).resolve().parent.parent
MENU_OPTION = ".select__menu .select__option"
COMBOBOX = 'input[role="combobox"]:not([id="country"])'


async def _find_live_job_url() -> str | None:
    source = GreenhouseSource(companies=["anthropic"])
    try:
        jobs = await source.list_jobs(SearchQuery())
    finally:
        await source.aclose()
    return str(jobs[0].apply_url or jobs[0].url) if jobs else None


async def _harvest(page, *, retry: bool) -> tuple[int, int]:
    """Return (comboboxes_with_options, total_comboboxes)."""
    ids = await page.eval_on_selector_all(
        COMBOBOX, "nodes => nodes.map(n => n.id)"
    )
    ok = 0
    for cid in ids:
        selector = f"#{cid}"
        got = await _try_open(page, selector)
        if not got and retry:
            await asyncio.sleep(0.4)
            got = await _try_open(page, selector)
        if got:
            ok += 1
    return ok, len(ids)


async def _try_open(page, selector: str) -> bool:
    try:
        await page.click(selector, timeout=2_000)
        await page.wait_for_selector(MENU_OPTION, timeout=2_000)
        await page.keyboard.press("Escape")
        return True
    except Exception:  # noqa: BLE001
        return False


async def _run_condition(url: str, label: str, *, networkidle: bool, retry: bool,
                         trials: int) -> None:
    results = []
    for _ in range(trials):
        browser = BrowserManager(
            user_data_dir=REPO_ROOT / "data" / "diag_browser_profile",
            headless=True,
        )
        await browser.launch()
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        if networkidle:
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:  # noqa: BLE001
                pass
        ok, total = await _harvest(page, retry=retry)
        results.append((ok, total))
        await browser.close()
    summary = ", ".join(f"{ok}/{total}" for ok, total in results)
    all_ok = all(ok == total and total > 0 for ok, total in results)
    print(f"  [{label}] {summary}   {'ALL OK' if all_ok else 'FLAKY'}")


async def main() -> int:
    url = await _find_live_job_url()
    if url is None:
        print("no live job")
        return 1
    print(f"URL: {url}\n")
    trials = 3
    print(f"comboboxes harvested with options (x{trials} trials each):")
    await _run_condition(url, "A no-wait      ", networkidle=False, retry=False, trials=trials)
    await _run_condition(url, "B networkidle  ", networkidle=True, retry=False, trials=trials)
    await _run_condition(url, "C idle+retry   ", networkidle=True, retry=True, trials=trials)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
