"""Verify the react-select interaction model before changing the extractor.

Two assumptions to confirm against a live Greenhouse form:
  1. Clicking a role=combobox input renders [role=option] nodes we can read.
  2. Clicking one of those options actually selects it (value sticks).

If both hold, the extractor can harvest options by opening each combobox, and
the executor can fill them by click-to-open + click-the-option.

Run: .venv/bin/python scripts/probe_combobox_fill.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from hamster.applicator.browser import BrowserManager
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.shared import SearchQuery

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


# Find react-select comboboxes: role=combobox + aria-haspopup. Returns their
# selectors (by id) and labels.
_FIND_COMBOBOXES_JS = r"""
() => {
    const out = [];
    document.querySelectorAll('input[role="combobox"][aria-haspopup="true"]').forEach((el) => {
        let label = el.getAttribute('aria-label');
        const lb = el.getAttribute('aria-labelledby');
        if (!label && lb) {
            const ref = document.getElementById(lb);
            if (ref) label = ref.textContent.trim();
        }
        out.push({ id: el.id, label, value: el.value });
    });
    return out;
}
"""

# react-select renders options as div.select__option only after opening.
# We must NOT match [role=option] — the phone country-code widget keeps 246
# hidden li.iti__country[role=option] permanently in the DOM.
_READ_OPTIONS_JS = r"""
() => Array.from(document.querySelectorAll('.select__menu .select__option'))
    .map((o) => (o.textContent || '').trim())
    .filter(Boolean)
"""


async def main() -> int:
    url = await _find_live_job_url()
    if url is None:
        print("no live job")
        return 1
    print(f"URL: {url}\n")

    browser = BrowserManager(
        user_data_dir=REPO_ROOT / "data" / "probe_browser_profile",
        headless=True,
    )
    await browser.launch()
    page = await browser.new_page()
    await page.goto(url)
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(2)  # let React hydrate

    comboboxes = await page.evaluate(_FIND_COMBOBOXES_JS)
    # Skip the phone country-code widget — it's intl-tel-input, not react-select,
    # and ships a default (+1). The real questions are everything else.
    comboboxes = [c for c in comboboxes if c["id"] and c["id"] != "country"]
    print(f"=== {len(comboboxes)} react-select comboboxes (excl. phone) ===\n")

    # Assumption 1: harvest options for each by opening it.
    for combo in comboboxes:
        cid = combo["id"]
        selector = f"#{cid}"
        try:
            await page.click(selector, timeout=3000)
            await page.wait_for_selector(".select__menu .select__option", timeout=3000)
            options = await page.evaluate(_READ_OPTIONS_JS)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
        except Exception as error:  # noqa: BLE001
            options = []
            print(f"[{cid}] {combo['label']!r} -> OPEN FAILED: {error}")
            continue
        print(f"[{cid}] {combo['label']!r}")
        print(f"    options: {options}")
        print()

    # Assumption 2: pick an option on the first combobox and confirm it sticks.
    target = comboboxes[0] if comboboxes else None
    if target:
        selector = f"#{target['id']}"
        print(f"=== selecting an option on #{target['id']} ===")
        await page.click(selector, timeout=3000)
        await page.wait_for_selector(".select__menu .select__option", timeout=3000)
        first_option = page.locator(".select__menu .select__option").first
        chosen_text = (await first_option.text_content() or "").strip()
        await first_option.click()
        await asyncio.sleep(0.5)
        # react-select reflects the choice in the container's text / data-value.
        container_text = await page.evaluate(
            f"""() => {{
                const el = document.getElementById({target['id']!r});
                const container = el.closest('.select__control, [class*="control"]');
                return container ? container.textContent.trim() : null;
            }}"""
        )
        print(f"    chose: {chosen_text!r}")
        print(f"    container now shows: {container_text!r}")
        print(f"    MATCH: {chosen_text and chosen_text in (container_text or '')}")

    await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
