"""Validate a LIBRARY-AGNOSTIC dropdown-detection strategy across many ATS.

Goal is NOT to learn what Lever/Ashby specifically look like and special-case
them. It's to confirm one generic strategy — built on web standards (native
<select>, ARIA combobox/listbox/option roles), never on a library's private
CSS class — detects the interactive controls on arbitrary application forms.
These sites are just samples; more will come.

For each live apply form (fetched dynamically, not hard-coded), we run several
candidate detection predicates and report what each finds, so we can see which
generic signals give coverage and where a fallback is still needed. Nothing is
ever submitted.

Run: .venv/bin/python scripts/probe_generic_forms.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from hamster.applicator.browser import BrowserManager
from hamster.job_discovery.sources.ashby import AshbySource
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.job_discovery.sources.lever import LeverSource
from hamster.shared import SearchQuery

REPO_ROOT = Path(__file__).resolve().parent.parent

# (label, source class, candidate company slugs). We try slugs in order until
# one yields a live posting, so the probe doesn't depend on a single open req.
SOURCES = [
    ("greenhouse", GreenhouseSource, ["anthropic", "stripe", "databricks"]),
    ("lever", LeverSource, ["spotify", "netflix", "palantir"]),
    ("ashby", AshbySource, ["openai", "ramp", "linear", "vercel"]),
]

# Candidate GENERIC detectors. Each is a CSS selector built only on HTML/ARIA
# standards — no react-select / MUI / library class names. We measure how many
# matches each finds per form so we can choose the detection layer by evidence.
GENERIC_DETECTORS = {
    "native_select": "select",
    "aria_combobox": '[role="combobox"]',
    "aria_haspopup_listbox": '[aria-haspopup="listbox"]',
    "aria_listbox": '[role="listbox"]',
    "text_input": 'input[type="text"], input:not([type])',
    "textarea": "textarea",
    "file_input": 'input[type="file"]',
    "radio": 'input[type="radio"]',
    "checkbox": 'input[type="checkbox"]',
    # A custom dropdown trigger that is NOT a native control: a button/div that
    # opens a listbox. Standards-based, library-agnostic.
    "custom_dropdown_trigger": (
        'button[aria-haspopup="listbox"], [role="combobox"], '
        'button[aria-expanded], [aria-haspopup="menu"]'
    ),
}

_SURVEY_JS = r"""
(detectors) => {
    const counts = {};
    for (const [name, selector] of Object.entries(detectors)) {
        try { counts[name] = document.querySelectorAll(selector).length; }
        catch (e) { counts[name] = 'BAD_SELECTOR'; }
    }
    // For anything that looks like a custom dropdown, capture standards-only
    // attributes (NO class names) so we can see if a generic open+read works.
    const customs = [];
    const seen = new Set();
    document.querySelectorAll('[role="combobox"], [aria-haspopup="listbox"], button[aria-expanded]').forEach((el) => {
        if (customs.length >= 6) return;
        const key = el.outerHTML.slice(0, 40);
        if (seen.has(key)) return;
        seen.add(key);
        customs.push({
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role'),
            haspopup: el.getAttribute('aria-haspopup'),
            expanded: el.getAttribute('aria-expanded'),
            controls: el.getAttribute('aria-controls'),
            labelledby: el.getAttribute('aria-labelledby'),
        });
    });
    return { counts, customs };
}
"""


async def _find_apply_url(label, source_cls, slugs):
    for slug in slugs:
        source = source_cls(companies=[slug])
        try:
            jobs = await source.list_jobs(SearchQuery())
        except Exception:  # noqa: BLE001
            await source.aclose()
            continue
        await source.aclose()
        if jobs:
            job = jobs[0]
            return str(job.apply_url or job.url), job.title
    return None, None


async def main() -> int:
    browser = BrowserManager(
        user_data_dir=REPO_ROOT / "data" / "probe_browser_profile",
        headless=True,
    )
    await browser.launch()
    for label, source_cls, slugs in SOURCES:
        url, title = await _find_apply_url(label, source_cls, slugs)
        if url is None:
            print(f"\n=== {label} === no live posting")
            continue
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30_000)
            await page.wait_for_load_state("domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(2)
            result = await page.evaluate(_SURVEY_JS, GENERIC_DETECTORS)
            print(f"\n=== {label} ===\n{title}\n{url}")
            print("generic-detector counts:", json.dumps(result["counts"]))
            print("custom-dropdown samples (standards attrs only):")
            for custom in result["customs"]:
                print("  ", json.dumps(custom, ensure_ascii=False))
            if not result["customs"]:
                print("  (none — controls are native or not yet rendered)")
        except Exception as error:  # noqa: BLE001
            print(f"\n=== {label} === FAILED: {error}")
        finally:
            await page.close()
    await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
