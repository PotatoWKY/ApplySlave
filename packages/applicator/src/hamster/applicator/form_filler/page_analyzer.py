"""Identify what kind of page we're on.

Tries cheap rule-based heuristics first (no LLM cost) and only falls back to
the model when rules can't decide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hamster.applicator.llm import DefaultPromptBuilder
from hamster.shared import (
    ElementType,
    LLMClient,
    PageAnalysis,
    PageDOM,
    PageType,
)

logger = logging.getLogger(__name__)


@dataclass
class RuleBasedPageAnalyzer:
    """Page classifier: DOM heuristics first, optional LLM fallback.

    The rules are cheap and cover the common, well-structured ATS pages.
    When they can't decide (`analyze_sync` returns None) and an `llm_client`
    was provided, the model classifies the page instead; without a client, or
    if the model errors, we degrade to UNKNOWN — so behavior is unchanged when
    no LLM is wired in.
    """

    llm_client: LLMClient | None = None
    prompt_builder: DefaultPromptBuilder | None = None

    def analyze_sync(self, dom: PageDOM) -> PageAnalysis | None:
        """Return an analysis, or None if rules can't classify the page."""
        url_lower = dom.url.lower()
        if any(needle in url_lower for needle in ("/login", "signin", "sign_in")):
            return PageAnalysis(
                page_type=PageType.LOGIN,
                confidence=0.9,
                reasoning="URL path hint",
            )

        input_elements = [
            el
            for el in dom.elements
            if el.element_type
            in {
                ElementType.INPUT_TEXT,
                ElementType.INPUT_EMAIL,
                ElementType.INPUT_TEL,
                ElementType.INPUT_FILE,
                ElementType.TEXTAREA,
                ElementType.SELECT,
            }
        ]
        has_submit = any(
            el.element_type is ElementType.BUTTON
            and (el.label or "").lower()
            .replace(" ", "")
            in {"submit", "submitapplication", "apply", "applynow", "send"}
            for el in dom.elements
        )
        has_file_upload = any(
            el.element_type is ElementType.INPUT_FILE for el in dom.elements
        )

        if len(input_elements) >= 3 and (has_submit or has_file_upload):
            return PageAnalysis(
                page_type=PageType.APPLICATION_FORM,
                confidence=0.85,
                reasoning="3+ inputs plus submit/upload",
            )

        # Confirmation pages tend to have few inputs and success-ish text
        title_lower = dom.title.lower()
        confirmation_hints = ("thank", "received", "submitted", "confirmed")
        if not input_elements and any(hint in title_lower for hint in confirmation_hints):
            return PageAnalysis(
                page_type=PageType.CONFIRMATION,
                confidence=0.7,
                reasoning="No form + success-style title",
            )

        return None

    async def analyze(self, dom: PageDOM) -> PageAnalysis:
        """Classify the page: rules first, LLM fallback, then UNKNOWN."""
        rule_based = self.analyze_sync(dom)
        if rule_based is not None:
            return rule_based

        if self.llm_client is not None:
            llm_result = await self._analyze_with_llm(dom)
            if llm_result is not None:
                return llm_result

        return PageAnalysis(
            page_type=PageType.UNKNOWN,
            confidence=0.3,
            reasoning="No matching rule",
        )

    async def _analyze_with_llm(self, dom: PageDOM) -> PageAnalysis | None:
        """Ask the model to classify the page. Returns None on any failure."""
        assert self.llm_client is not None
        builder = self.prompt_builder or DefaultPromptBuilder()
        prompt = builder.build_page_analysis_prompt(dom)
        try:
            raw = await self.llm_client.chat_json(prompt)
            return PageAnalysis.model_validate(raw)
        except Exception as error:
            logger.warning("LLM page analysis failed: %s", error)
            return None
