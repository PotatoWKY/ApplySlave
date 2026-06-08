"""Diagnose why fields stay empty on a real Greenhouse form.

Dumps the full pipeline's intermediate data so we can see exactly where
filling breaks:

  1. Every DOM element the extractor sees (type / label / required / options /
     selector).
  2. The exact prompt sent to the LLM.
  3. The raw JSON the LLM returns.
  4. The final FillPlan (actions + unmapped_fields + confidence).
  5. Per-action execution result (filled OK vs failed, with the error).

Headless — we're reading data, not watching. Run:
    .venv/bin/python scripts/diagnose_greenhouse.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from hamster.applicator.browser import ActionExecutor, BrowserManager, DOMExtractor
from hamster.applicator.form_filler import FormMapper
from hamster.applicator.llm import DefaultPromptBuilder, LLMClient, ModelManager
from hamster.backend.dependencies import get_data_dir, get_profile_store
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.shared import ElementType, SearchQuery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("diagnose")

REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_COMPANIES = ["anthropic", "stripe", "databricks", "figma", "ramp"]


async def _find_live_job_url() -> tuple[str, str, str] | None:
    for company in CANDIDATE_COMPANIES:
        source = GreenhouseSource(companies=[company])
        try:
            jobs = await source.list_jobs(SearchQuery())
        except Exception as error:  # noqa: BLE001
            logger.warning("fetch %s failed: %s", company, error)
            await source.aclose()
            continue
        await source.aclose()
        if jobs:
            job = jobs[0]
            return str(job.apply_url or job.url), job.company, job.title
    return None


def _hr(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def main() -> int:
    profile = get_profile_store().load_profile()
    if profile is None:
        logger.error("No saved profile")
        return 1

    found = await _find_live_job_url()
    if found is None:
        logger.error("No live Greenhouse job")
        return 1
    url, company, title = found
    print(f"Target: {title} @ {company}\nURL: {url}")

    browser = BrowserManager(
        user_data_dir=REPO_ROOT / "data" / "diag_browser_profile",
        headless=True,
    )
    await browser.launch()
    page = await browser.new_page()
    await page.goto(url)

    extractor = DOMExtractor()
    dom = await extractor.extract(page)

    _hr(f"DOM ELEMENTS ({len(dom.elements)})")
    for el in dom.elements:
        line = (
            f"[{el.element_type.value}] id={el.id} "
            f"required={el.required} label={el.label!r}"
        )
        if el.options:
            line += f" options={el.options}"
        if el.current_value:
            line += f" value={el.current_value!r}"
        line += f"\n    selector: {el.selector}"
        print(line)

    # Counts by type so we see how many selects/inputs exist.
    counts: dict[str, int] = {}
    for el in dom.elements:
        counts[el.element_type.value] = counts.get(el.element_type.value, 0) + 1
    _hr("ELEMENT TYPE COUNTS")
    print(json.dumps(counts, indent=2))

    # LLM mapping
    manager = ModelManager(data_dir=get_data_dir())
    if not manager.is_installed():
        logger.error("Model not installed; cannot diagnose LLM path")
        await browser.close()
        return 1

    builder = DefaultPromptBuilder()
    prompt = builder.build_form_mapping_prompt(dom, profile)
    _hr("LLM PROMPT (form mapping)")
    print(prompt)

    llm = LLMClient(model_path=manager.model_path)
    _hr("LLM RAW RESPONSE")
    try:
        raw = await llm.chat_json(prompt)
        print(json.dumps(raw, indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(f"LLM call failed: {error}")
        raw = None

    # Full FormMapper plan (deterministic + LLM merge)
    mapper = FormMapper(llm_client=llm)
    plan = await mapper.plan(dom, profile)
    _hr("FINAL FILL PLAN")
    print(f"confidence: {plan.confidence}")
    print(f"reasoning: {plan.reasoning}")
    print(f"unmapped_fields ({len(plan.unmapped_fields)}): {plan.unmapped_fields}")
    print(f"actions ({len(plan.actions)}):")
    for action in plan.actions:
        print(f"  {action.type.value} {action.selector} = {action.value!r}")

    # Try executing each action and report per-action success
    _hr("PER-ACTION EXECUTION")
    executor = ActionExecutor()
    for action in plan.actions:
        try:
            await executor.execute(page, action)
            print(f"  OK   {action.type.value} {action.selector}")
        except Exception as error:  # noqa: BLE001
            print(f"  FAIL {action.type.value} {action.selector}: {error}")

    # Which required fields end up with no action at all?
    action_selectors = {a.selector for a in plan.actions}
    _hr("REQUIRED FIELDS WITH NO ACTION")
    for el in dom.elements:
        if (
            el.required
            and el.element_type
            not in {ElementType.BUTTON, ElementType.INPUT_FILE}
            and el.selector not in action_selectors
        ):
            opts = f" options={el.options}" if el.options else ""
            print(f"  [{el.element_type.value}] {el.label!r}{opts}")

    await asyncio.sleep(1)
    await browser.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
