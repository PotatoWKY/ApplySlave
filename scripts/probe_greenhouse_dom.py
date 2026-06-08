"""Probe the raw HTML structure of Greenhouse's custom dropdowns.

The dry-run showed visa / in-person / relocation questions render as a text
input + sibling button rather than a native <select>, so our extractor sees
no options. Before changing the extractor we need the GROUND TRUTH: what
attributes do these widgets actually carry (role, aria-*, data-*), and where
do the option values live in the DOM?

Dumps, for each text input whose label ends in '?' or '*' (i.e. a question),
the outerHTML of the input and its surrounding container, plus any
role=option / listbox nodes found after clicking the control.

Run: .venv/bin/python scripts/probe_greenhouse_dom.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from hamster.applicator.browser import BrowserManager
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


_PROBE_JS = r"""
() => {
    const report = [];
    // Find inputs whose associated label looks like a question.
    const inputs = Array.from(document.querySelectorAll('input:not([type=hidden])'));
    for (const el of inputs) {
        let labelText = '';
        if (el.id) {
            const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (lab) labelText = lab.textContent.trim();
        }
        // Collect the attributes that hint at a combobox.
        const attrs = {};
        for (const a of el.attributes) attrs[a.name] = a.value;
        // Climb to a container that might hold the popup / options.
        const container = el.closest('div[class*="select"], div[class*="Select"], div[class*="combobox"], fieldset, div');
        const containerHTML = container ? container.outerHTML.slice(0, 900) : null;
        report.push({
            label: labelText,
            id: el.id,
            role: el.getAttribute('role'),
            ariaHasPopup: el.getAttribute('aria-haspopup'),
            ariaExpanded: el.getAttribute('aria-expanded'),
            ariaAutocomplete: el.getAttribute('aria-autocomplete'),
            readOnly: el.readOnly,
            autocomplete: el.getAttribute('autocomplete'),
            attrs,
            containerHTML,
        });
    }
    return report;
}
"""

_OPTIONS_AFTER_CLICK_JS = r"""
() => {
    const opts = Array.from(
        document.querySelectorAll('[role="option"], [role="listbox"] li, [class*="option"]')
    ).slice(0, 30).map((o) => ({
        role: o.getAttribute('role'),
        text: (o.textContent || '').trim().slice(0, 80),
        cls: o.className,
    }));
    return opts;
}
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

    report = await page.evaluate(_PROBE_JS)
    # Only show the question-like ones (label ends with ? or *), to cut noise.
    questions = [
        r
        for r in report
        if r["label"] and (r["label"].rstrip().endswith("?") or "*" in r["label"])
    ]
    print(f"=== {len(questions)} question-like inputs ===\n")
    for entry in questions:
        print(f"LABEL: {entry['label']}")
        print(f"  id={entry['id']} role={entry['role']} "
              f"aria-haspopup={entry['ariaHasPopup']} "
              f"aria-autocomplete={entry['ariaAutocomplete']} "
              f"readonly={entry['readOnly']} autocomplete={entry['autocomplete']}")
        print(f"  attrs={json.dumps(entry['attrs'])}")
        print(f"  container={entry['containerHTML']}")
        print()

    # Try clicking the first question control and see what options appear.
    if questions:
        first_id = questions[0]["id"]
        if first_id:
            print(f"=== clicking #{first_id} to reveal options ===")
            try:
                await page.click(f"#{first_id}", timeout=3000)
                await asyncio.sleep(1)
                opts = await page.evaluate(_OPTIONS_AFTER_CLICK_JS)
                print(json.dumps(opts, indent=2, ensure_ascii=False))
            except Exception as error:  # noqa: BLE001
                print(f"click failed: {error}")

    await browser.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
