"""Shared option-matching logic.

The form mapper validates a chosen value against an element's options, and the
action executor later clicks the matching option. Both must agree on what
"matches" means, or the mapper could keep a value the executor then can't find
(or vice-versa). Keeping the rule in one place stops the two from drifting.
"""

from __future__ import annotations

import re

# Standards-first selector for the options of an opened custom dropdown. W3C
# [role="option"] first (Greenhouse, Ashby, headless-ui, MUI, ...); react-select's
# private `.select__option` only as a compat fallback. Shared by the extractor's
# option harvest and the executor's click so the two never target different
# nodes.
#
# The `:visible` pseudo-class is essential: pages often keep UNRELATED, hidden
# role=option nodes permanently in the DOM (e.g. intl-tel-input's 246 country
# <li role="option"> for the phone widget). Without :visible, waiting for
# [role=option] resolves instantly against those hidden nodes and we never see
# the dropdown we actually opened. Filtering to visible options targets exactly
# the menu that just opened, on any library.
COMBOBOX_OPTION_SELECTOR = (
    '[role="option"]:visible, .select__menu .select__option:visible'
)


def normalize_option(text: str) -> str:
    return text.strip().casefold()


def first_matching_index(target: str, options: list[str]) -> int | None:
    """Index of the option ``target`` resolves to, or None.

    ``target`` must already be normalized (see ``normalize_option``). Exact
    match wins; the fallback requires ``target`` to appear as a whole WORD in
    the option, not an arbitrary substring. Substring matching is unsafe for
    short answers — "No" is a substring of "I kNOw the role is onsite" and of
    "NOne of the above", which would silently select the opposite option. The
    word-boundary fallback still handles options that carry extra wording
    (e.g. value "Yes" matching option "Yes, I agree"). Earlier options win, so
    the choice is deterministic.
    """
    if not target:
        return None
    normalized = [normalize_option(option) for option in options]
    for index, option in enumerate(normalized):
        if option == target:
            return index
    pattern = re.compile(rf"\b{re.escape(target)}\b")
    for index, option in enumerate(normalized):
        if pattern.search(option):
            return index
    return None


def value_matches_option(value: str | None, options: list[str]) -> bool:
    """True if ``value`` resolves to one of ``options``.

    Exact (trimmed, case-insensitive) match first, then a case-insensitive
    containment fallback for option labels that carry extra wording — the same
    two-step the executor uses when it clicks the option.
    """
    if value is None:
        return False
    return first_matching_index(normalize_option(value), options) is not None
