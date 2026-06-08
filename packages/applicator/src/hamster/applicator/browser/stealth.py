"""Init scripts used to mask automation fingerprints.

Ported from the v1 implementation. Applied to every browser context on start.
"""

from __future__ import annotations

STEALTH_INIT_SCRIPT = """
() => {
    // 1. Hide webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. Remove Playwright injection markers
    delete window.__playwright__binding__;
    delete window.__pwInitScripts;

    // 3. Fake some plugins (headless Chrome usually has none)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // 4. Fake languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // 5. Ensure chrome.runtime exists
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {};
    }

    // 6. Patch permissions.query for notifications
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }
}
"""
