"""Playwright wrappers: browser manager, DOM extractor, action executor."""

from hamster.applicator.browser.action_executor import ActionError, ActionExecutor
from hamster.applicator.browser.dom_extractor import DOMExtractor
from hamster.applicator.browser.manager import BrowserManager

__all__ = ["ActionError", "ActionExecutor", "BrowserManager", "DOMExtractor"]
