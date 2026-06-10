"""ActionExecutor tests against the fixture apply form."""

from __future__ import annotations

from pathlib import Path

import pytest
from hamster.applicator.browser import (
    ActionError,
    ActionExecutor,
    BrowserManager,
)
from hamster.shared import ActionType, PageAction


async def test_fill_and_submit(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4\n%EOF\n")

    actions = [
        PageAction(type=ActionType.FILL, selector="#first-name", value="San"),
        PageAction(type=ActionType.FILL, selector="#last-name", value="Zhang"),
        PageAction(type=ActionType.FILL, selector="#email", value="san@example.com"),
        PageAction(type=ActionType.SELECT, selector="#experience", value="3-5 years"),
        PageAction(
            type=ActionType.FILL,
            selector="#cover-letter",
            value="I am excited to apply.",
        ),
        PageAction(
            type=ActionType.UPLOAD,
            selector="#resume",
            value=str(resume_file),
        ),
        PageAction(type=ActionType.CHECK, selector="#sponsorship"),
    ]

    executor = ActionExecutor()
    failures = await executor.run_plan(page, actions)
    assert failures == []

    # Verify DOM state reflects the actions
    assert await page.input_value("#first-name") == "San"
    assert await page.input_value("#email") == "san@example.com"
    assert await page.input_value("#experience") == "3-5"
    assert await page.input_value("#cover-letter") == "I am excited to apply."
    assert await page.is_checked("#sponsorship")


async def test_missing_upload_source_raises(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    missing_path = tmp_path / "nope.pdf"
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(
                type=ActionType.UPLOAD,
                selector="#resume",
                value=str(missing_path),
            ),
        )


async def test_select_missing_value_raises(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(type=ActionType.SELECT, selector="#experience"),
        )


async def test_select_combobox_picks_option(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    await executor.execute(
        page,
        PageAction(
            type=ActionType.SELECT_COMBOBOX, selector="#relocation", value="Yes"
        ),
    )

    # The emulated react-select writes the chosen text back to the control.
    assert await page.input_value("#relocation") == "Yes"
    assert (
        await page.get_attribute(".select__value", "data-value") == "Yes"
    )


async def test_select_combobox_no_matching_option_raises(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(
                type=ActionType.SELECT_COMBOBOX,
                selector="#relocation",
                value="Maybe someday",
            ),
        )


async def test_select_combobox_missing_value_raises(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(type=ActionType.SELECT_COMBOBOX, selector="#relocation"),
        )


async def test_run_plan_collects_failure_and_continues(
    browser: BrowserManager, apply_form_url: str
) -> None:
    """One failing action must not abort the rest of the plan.

    A fill against a non-existent selector fails, but the valid fill after it
    must still land, and run_plan returns the failure instead of raising.
    """
    page = await browser.new_page()
    await page.goto(apply_form_url)

    actions = [
        PageAction(type=ActionType.FILL, selector="#first-name", value="San"),
        PageAction(type=ActionType.FILL, selector="#does-not-exist", value="x"),
        PageAction(type=ActionType.FILL, selector="#last-name", value="Zhang"),
    ]

    executor = ActionExecutor()
    failures = await executor.run_plan(page, actions)

    assert len(failures) == 1
    assert failures[0].selector == "#does-not-exist"
    assert failures[0].action_type is ActionType.FILL
    # The valid fields on either side of the failure still filled.
    assert await page.input_value("#first-name") == "San"
    assert await page.input_value("#last-name") == "Zhang"


async def test_select_combobox_picks_option_aria_portal(
    browser: BrowserManager, aria_portal_form_url: str
) -> None:
    """A pure-ARIA combobox (options in a body-level portal, NO react-select
    classes) is operable via the standards-first selector."""
    page = await browser.new_page()
    await page.goto(aria_portal_form_url)

    executor = ActionExecutor()
    await executor.execute(
        page,
        PageAction(
            type=ActionType.SELECT_COMBOBOX, selector="#work-auth", value="Yes"
        ),
    )
    assert await page.input_value("#work-auth") == "Yes"


async def test_click_radio_option(
    browser: BrowserManager, apply_form_url: str
) -> None:
    """A radio choice fills via CLICK on the concrete option selector (as the
    mapper rewrites it), and selecting one deselects its siblings."""
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    await executor.execute(
        page, PageAction(type=ActionType.CLICK, selector="#loc_hybrid")
    )
    assert await page.is_checked("#loc_hybrid")
    assert not await page.is_checked("#loc_remote")
    assert not await page.is_checked("#loc_onsite")


async def test_check_standalone_checkbox(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    await executor.execute(
        page, PageAction(type=ActionType.CHECK, selector="#veteran")
    )
    assert await page.is_checked("#veteran")
