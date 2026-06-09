"""Extract interactable form elements from a rendered page.

Runs a small JavaScript snippet inside the page to walk the DOM, resolve
labels, and produce a stable selector per element. The output fits the shared
PageDOM / PageElement models so the LLM and executor can consume it directly.
"""

from __future__ import annotations

import logging

from hamster.shared import ElementType, PageDOM, PageElement
from playwright.async_api import Page

logger = logging.getLogger(__name__)


# JS executed in the page to collect candidate elements.
# Kept small on purpose; complex heuristics live on the Python side.
_EXTRACT_JS = r"""
() => {
    const out = [];

    function resolveLabel(el) {
        if (el.id) {
            const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (label) return label.textContent.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) {
            const clone = parentLabel.cloneNode(true);
            clone.querySelectorAll('input,select,textarea').forEach((x) => x.remove());
            const text = clone.textContent.trim();
            if (text) return text;
        }
        const aria = el.getAttribute('aria-label');
        if (aria) return aria;
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ref = document.getElementById(labelledBy);
            if (ref) return ref.textContent.trim();
        }
        return null;
    }

    function buildSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) {
            return el.tagName.toLowerCase() + `[name="${CSS.escape(el.name)}"]`;
        }
        // Fallback to a structural selector rooted at body
        const path = [];
        let cur = el;
        while (cur && cur !== document.body) {
            const parent = cur.parentElement;
            if (!parent) break;
            const siblings = Array.from(parent.children).filter(
                (c) => c.tagName === cur.tagName,
            );
            const idx = siblings.indexOf(cur) + 1;
            path.unshift(cur.tagName.toLowerCase() + ':nth-of-type(' + idx + ')');
            cur = parent;
        }
        return path.length ? path.join(' > ') : el.tagName.toLowerCase();
    }

    function isVisible(el) {
        if (el.type === 'file') return true;  // file inputs often hidden but needed
        return !!el.offsetParent;
    }

    function isInteractable(el) {
        // Skip elements the page itself marks as non-interactive. react-select
        // injects a hidden required="" mirror input (aria-hidden, tabindex=-1)
        // per dropdown purely for native form validation — it has no label and
        // no stable selector, and filling it does nothing but break.
        if (el.getAttribute('aria-hidden') === 'true') return false;
        if (el.tabIndex === -1 && el.type !== 'file') return false;
        return true;
    }

    document.querySelectorAll('input:not([type="hidden"])').forEach((el) => {
        if (!isVisible(el)) return;
        // JS-driven comboboxes (react-select) render as a text input with
        // role=combobox. They carry no options in the DOM until opened, so
        // they're collected separately below — skip them here.
        if (el.getAttribute('role') === 'combobox') return;
        if (!isInteractable(el)) return;
        out.push({
            tag: 'input',
            type: (el.type || 'text').toLowerCase(),
            label: resolveLabel(el),
            placeholder: el.placeholder || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            value: el.value || null,
            selector: buildSelector(el),
        });
    });

    // Comboboxes: role=combobox text inputs (react-select and similar). Options
    // are harvested on the Python side by opening each one. We exclude the
    // intl-tel-input phone country picker (selector #country) — it ships a
    // sensible default and isn't a question to answer.
    document.querySelectorAll('input[role="combobox"]').forEach((el) => {
        if (!isVisible(el)) return;
        if (el.id === 'country') return;
        out.push({
            tag: 'combobox',
            type: 'combobox',
            label: resolveLabel(el),
            placeholder: el.placeholder || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            value: el.value || null,
            selector: buildSelector(el),
        });
    });

    document.querySelectorAll('textarea').forEach((el) => {
        if (!isVisible(el)) return;
        out.push({
            tag: 'textarea',
            type: 'textarea',
            label: resolveLabel(el),
            placeholder: el.placeholder || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            value: el.value || null,
            selector: buildSelector(el),
        });
    });

    document.querySelectorAll('select').forEach((el) => {
        if (!isVisible(el)) return;
        const options = Array.from(el.options)
            .map((o) => o.text.trim())
            .filter(Boolean);
        out.push({
            tag: 'select',
            type: 'select',
            label: resolveLabel(el),
            placeholder: null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            options,
            value: el.value || null,
            selector: buildSelector(el),
        });
    });

    document.querySelectorAll('button, input[type="submit"]').forEach((el) => {
        if (!isVisible(el)) return;
        out.push({
            tag: el.tagName.toLowerCase() === 'button' ? 'button' : 'input',
            type: 'submit',
            text: el.textContent?.trim() || el.value || null,
            selector: buildSelector(el),
        });
    });

    return out;
}
"""


_TYPE_MAP = {
    ("input", "text"): ElementType.INPUT_TEXT,
    ("input", "email"): ElementType.INPUT_EMAIL,
    ("input", "tel"): ElementType.INPUT_TEL,
    ("input", "password"): ElementType.INPUT_PASSWORD,
    ("input", "file"): ElementType.INPUT_FILE,
    ("input", "checkbox"): ElementType.INPUT_CHECKBOX,
    ("input", "radio"): ElementType.INPUT_RADIO,
    ("input", "submit"): ElementType.BUTTON,
    ("button", "submit"): ElementType.BUTTON,
    ("select", "select"): ElementType.SELECT,
    ("combobox", "combobox"): ElementType.COMBOBOX,
    ("textarea", "textarea"): ElementType.TEXTAREA,
}

# react-select renders its options as `.select__option` inside a `.select__menu`
# popup, but only after the control is opened. These selectors drive the
# open-read-close harvest below.
_COMBOBOX_MENU_OPTION = ".select__menu .select__option"


def _classify(tag: str, raw_type: str | None) -> ElementType:
    key = (tag, (raw_type or "").lower())
    return _TYPE_MAP.get(key, ElementType.OTHER)


class DOMExtractor:
    """Pull structured page info from Playwright pages."""

    async def extract(self, page: Page) -> PageDOM:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception as error:  # noqa: BLE001 - timeouts are expected
            logger.debug("Continuing despite load-state timeout: %s", error)

        url = page.url
        title = await page.title()

        raw_elements = await page.evaluate(_EXTRACT_JS)

        elements: list[PageElement] = []
        for idx, raw in enumerate(raw_elements or []):
            tag = str(raw.get("tag") or "").lower()
            raw_type = raw.get("type")
            element_type = _classify(tag, raw_type)
            label = raw.get("label") or raw.get("text") or raw.get("placeholder")
            elements.append(
                PageElement(
                    id=f"el_{idx}",
                    element_type=element_type,
                    label=str(label).strip() if label else None,
                    placeholder=raw.get("placeholder") or None,
                    required=bool(raw.get("required")),
                    options=list(raw.get("options") or []),
                    current_value=raw.get("value") or None,
                    selector=str(raw.get("selector") or ""),
                )
            )

        await self._harvest_combobox_options(page, elements)

        logger.info("Extracted %d elements from %s", len(elements), url)
        return PageDOM(url=url, title=title, elements=elements)

    async def _harvest_combobox_options(
        self, page: Page, elements: list[PageElement]
    ) -> None:
        """Fill in `options` for combobox elements by opening each one.

        react-select only renders its options once the control is clicked, so
        we can't read them in the single DOM pass. For each combobox we open
        it, read the rendered option labels, then close it with Escape. A
        combobox we can't open is left with empty options — the mapper treats
        that as unmapped rather than guessing.
        """
        for element in elements:
            if element.element_type is not ElementType.COMBOBOX:
                continue
            try:
                await page.click(element.selector, timeout=3_000)
                await page.wait_for_selector(_COMBOBOX_MENU_OPTION, timeout=3_000)
                option_texts = await page.eval_on_selector_all(
                    _COMBOBOX_MENU_OPTION,
                    "nodes => nodes.map(n => (n.textContent || '').trim())"
                    ".filter(Boolean)",
                )
                await page.keyboard.press("Escape")
                element.options = list(option_texts)
                logger.debug(
                    "Combobox %s options: %s", element.selector, option_texts
                )
            except Exception as error:
                logger.warning(
                    "Failed to harvest options for combobox %s: %s",
                    element.selector,
                    error,
                )
