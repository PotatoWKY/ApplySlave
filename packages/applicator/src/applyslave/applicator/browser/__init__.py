"""Playwright wrappers: browser manager, DOM extractor, action executor."""

from applyslave.applicator.browser.action_executor import ActionError, ActionExecutor
from applyslave.applicator.browser.dom_extractor import DOMExtractor
from applyslave.applicator.browser.manager import BrowserManager

__all__ = ["ActionError", "ActionExecutor", "BrowserManager", "DOMExtractor"]
