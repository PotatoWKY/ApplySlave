"""Identify what kind of page we're on.

Tries cheap rule-based heuristics first (no LLM cost) and only falls back to
the model when rules can't decide.
"""

from __future__ import annotations

from hamster.shared import ElementType, PageAnalysis, PageDOM, PageType


class RuleBasedPageAnalyzer:
    """Fast, deterministic page classifier using DOM heuristics only."""

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
        """Async wrapper to match the PageAnalyzer protocol."""
        rule_based = self.analyze_sync(dom)
        if rule_based is not None:
            return rule_based
        return PageAnalysis(
            page_type=PageType.UNKNOWN,
            confidence=0.3,
            reasoning="No matching rule",
        )
