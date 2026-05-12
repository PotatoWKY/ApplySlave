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

from applyslave.applicator.llm import DefaultPromptBuilder
from applyslave.shared import (
    ActionType,
    ElementType,
    FillPlan,
    LLMClient,
    PageAction,
    PageDOM,
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

        return self._merge(deterministic_plan, llm_plan)

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

    def _merge(self, base: FillPlan, extra: FillPlan) -> FillPlan:
        """Use deterministic actions for fields they already covered, LLM for the rest."""
        covered_selectors = {action.selector for action in base.actions}
        merged_actions = list(base.actions)
        for action in extra.actions:
            if action.selector not in covered_selectors:
                merged_actions.append(action)
                covered_selectors.add(action.selector)

        remaining_unmapped = [
            field
            for field in base.unmapped_fields
            if field not in (extra.unmapped_fields or [])
        ]
        return FillPlan(
            actions=merged_actions,
            unmapped_fields=remaining_unmapped,
            confidence=min(base.confidence, extra.confidence),
            reasoning="rule-based + llm",
        )


_FILLABLE_TYPES = {
    ElementType.INPUT_TEXT,
    ElementType.INPUT_EMAIL,
    ElementType.INPUT_TEL,
    ElementType.TEXTAREA,
    ElementType.SELECT,
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
