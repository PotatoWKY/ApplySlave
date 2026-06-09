"""Map a form's fields to a user's profile, producing an executable plan.

The mapper combines:

1. Deterministic matches on field label ("email" → profile.email, etc).
2. An optional LLM fallback for fuzzy cases (open-ended questions, unusual
   label wording). The LLM side is pluggable via the `LLMClient` protocol so
   tests can inject a static stub.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hamster.applicator.llm import DefaultPromptBuilder
from hamster.applicator.matching import value_matches_option
from hamster.shared import (
    ActionType,
    ElementType,
    FillPlan,
    LLMClient,
    PageAction,
    PageDOM,
    PageElement,
    UserProfile,
)

logger = logging.getLogger(__name__)


_LABEL_ALIASES = {
    "first_name": {"first name", "given name", "firstname"},
    "last_name": {"last name", "family name", "surname", "lastname"},
    "email": {"email", "email address", "e-mail"},
    "phone": {"phone", "phone number", "mobile", "telephone"},
    "location": {"location", "city", "current city"},
    "linkedin_url": {"linkedin", "linkedin profile", "linkedin url"},
    "github_url": {"github", "github profile", "github url"},
}


def _normalize(text: str) -> str:
    return text.strip().lower()


@dataclass
class FormMapper:
    """Build a FillPlan by combining deterministic matches + an LLM fallback."""

    llm_client: LLMClient | None = None
    prompt_builder: DefaultPromptBuilder | None = None

    async def plan(self, dom: PageDOM, profile: UserProfile) -> FillPlan:
        deterministic_plan = self._deterministic(dom, profile)

        if not deterministic_plan.unmapped_fields or self.llm_client is None:
            return deterministic_plan

        builder = self.prompt_builder or DefaultPromptBuilder()
        prompt = builder.build_form_mapping_prompt(dom, profile)
        try:
            raw = await self.llm_client.chat_json(prompt)
            llm_plan = FillPlan.model_validate(raw)
        except Exception as error:  # noqa: BLE001
            logger.warning("LLM fallback failed: %s", error)
            return deterministic_plan

        return self._merge(dom, deterministic_plan, llm_plan)

    # --- private ---------------------------------------------------------

    def _deterministic(self, dom: PageDOM, profile: UserProfile) -> FillPlan:
        actions: list[PageAction] = []
        unmapped: list[str] = []
        profile_map = _build_profile_lookup(profile)

        for element in dom.elements:
            if element.element_type is ElementType.BUTTON:
                continue
            mapped = self._match_element(element, profile_map, profile)
            if mapped is not None:
                actions.append(mapped)
            elif element.element_type in _FILLABLE_TYPES and (element.label or ""):
                unmapped.append(element.label or element.id)

        return FillPlan(
            actions=actions,
            unmapped_fields=unmapped,
            confidence=1.0 if not unmapped else 0.6,
            reasoning="rule-based",
        )

    def _match_element(
        self,
        element,
        profile_map: dict[str, str | None],
        profile: UserProfile,
    ) -> PageAction | None:
        if element.element_type is ElementType.INPUT_FILE:
            if profile.resume_path:
                return PageAction(
                    type=ActionType.UPLOAD,
                    selector=element.selector,
                    value=profile.resume_path,
                )
            return None

        # Choice controls (native select / combobox) must never be free-text
        # filled from a label alias. Their value has to be one of the options,
        # which only the LLM can pick semantically — e.g. "Are you open to
        # relocation?" must not get the profile's location just because the
        # label contains the substring "location".
        if element.element_type in (ElementType.SELECT, ElementType.COMBOBOX):
            return None

        label = _normalize(element.label or element.placeholder or "")
        if not label:
            return None

        for attr, aliases in _LABEL_ALIASES.items():
            if label in aliases or any(alias in label for alias in aliases):
                value = profile_map.get(attr)
                if value is None:
                    return None
                return PageAction(
                    type=ActionType.FILL,
                    selector=element.selector,
                    value=value,
                )

        if element.element_type is ElementType.INPUT_EMAIL:
            return PageAction(
                type=ActionType.FILL,
                selector=element.selector,
                value=profile.email,
            )
        if element.element_type is ElementType.INPUT_TEL and profile.phone:
            return PageAction(
                type=ActionType.FILL,
                selector=element.selector,
                value=profile.phone,
            )

        return None

    def _merge(self, dom: PageDOM, base: FillPlan, extra: FillPlan) -> FillPlan:
        """Combine deterministic + LLM actions, then recompute what's left.

        Both unmapped and confidence are derived from the DOM by selector —
        the single source of truth for "is this element covered?". The earlier
        version diffed two *label* lists while actions carry *selectors*, so a
        field the LLM filled (by selector) was never removed from unmapped,
        and confidence (min of the two passes) ignored the LLM's work.
        """
        element_by_selector = {
            element.selector: element for element in dom.elements
        }
        type_by_selector = {
            selector: element.element_type
            for selector, element in element_by_selector.items()
        }
        covered_selectors = {action.selector for action in base.actions}
        merged_actions = list(base.actions)
        for action in extra.actions:
            if action.selector in covered_selectors:
                continue
            corrected = self._correct_action_type(action, type_by_selector)
            if not self._action_value_is_valid(corrected, element_by_selector):
                # Drop a choice value the element can't accept (an LLM
                # invention) rather than send it downstream to a guaranteed
                # execution failure; the field stays unmapped.
                continue
            merged_actions.append(corrected)
            covered_selectors.add(corrected.selector)

        # A fillable element is unmapped iff no action targets its selector.
        # Comboboxes whose options couldn't be harvested are neither counted as
        # covered nor as unmapped: an extraction failure shouldn't masquerade as
        # missing profile data or drag confidence down.
        fillable = [
            element
            for element in dom.elements
            if element.element_type in _FILLABLE_TYPES
            and not element.harvest_failed
        ]
        remaining_unmapped = [
            element.label or element.id
            for element in fillable
            if element.selector not in covered_selectors
        ]

        # Confidence = fraction of fillable fields we actually covered.
        if not fillable:
            confidence = 1.0
        else:
            covered_count = len(fillable) - len(remaining_unmapped)
            confidence = covered_count / len(fillable)
        return FillPlan(
            actions=merged_actions,
            unmapped_fields=remaining_unmapped,
            confidence=confidence,
            reasoning="rule-based + llm",
        )

    def _action_value_is_valid(
        self,
        action: PageAction,
        element_by_selector: dict[str, PageElement],
    ) -> bool:
        """Reject a combobox action whose value isn't a real option.

        Scoped to SELECT_COMBOBOX (react-select), where the harvested options
        ARE the only valid click targets, so an out-of-range value is doomed
        and worth dropping. Native ``<select>`` is intentionally not validated
        here: the extractor stores option text but the executor's _select also
        falls back to the ``<option value>`` attribute, so a value-attr match
        would be wrongly rejected. If options came back empty (harvest
        failure), we let it pass through — the executor is non-fatal and a
        human reviews the screenshot, so failing loud beats silently dropping
        the field. Non-combobox actions are always allowed.
        """
        if action.type is not ActionType.SELECT_COMBOBOX:
            return True
        element = element_by_selector.get(action.selector)
        if element is None or not element.options:
            return True
        return value_matches_option(action.value, element.options)

    def _correct_action_type(
        self,
        action: PageAction,
        type_by_selector: dict[str, ElementType],
    ) -> PageAction:
        """Force a fill action's type to match the element's real type.

        Whether a control is a native ``<select>`` or a JS combobox is known
        for certain at extraction time, so we don't let the LLM decide it — a
        combobox element always gets SELECT_COMBOBOX, a native select gets
        SELECT, regardless of what the model emitted. This removes a whole
        class of "Element is not a <select>" failures. Non-value-setting
        actions (click/check/upload) are left untouched.
        """
        element_type = type_by_selector.get(action.selector)
        if element_type is ElementType.COMBOBOX:
            desired = ActionType.SELECT_COMBOBOX
        elif element_type is ElementType.SELECT:
            desired = ActionType.SELECT
        else:
            return action
        if action.type is desired:
            return action
        return action.model_copy(update={"type": desired})


_FILLABLE_TYPES = {
    ElementType.INPUT_TEXT,
    ElementType.INPUT_EMAIL,
    ElementType.INPUT_TEL,
    ElementType.TEXTAREA,
    ElementType.SELECT,
    ElementType.COMBOBOX,
}


def _build_profile_lookup(profile: UserProfile) -> dict[str, str | None]:
    return {
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
    }
