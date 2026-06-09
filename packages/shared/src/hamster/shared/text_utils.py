"""Text helpers shared across packages.

Lives in ``shared`` (not in applicator) so job-discovery can use it too:
job-discovery has no dependency on applicator, so importing a cleaner from
there would violate the package boundary. ``shared`` depends only on pydantic,
so every package can import this cleanly.
"""

from __future__ import annotations

import html
import re

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_job_description(raw_html: str | None, max_chars: int = 2000) -> str | None:
    """Turn an ATS job description (often HTML-escaped) into capped plain text.

    Greenhouse returns the posting body under ``content`` as HTML with its
    angle brackets entity-escaped (``&lt;div&gt;…``), ~10KB. We unescape it,
    drop script/style bodies, strip tags, collapse whitespace, and truncate at
    a word boundary so it can be injected into the LLM prompt without blowing
    the context budget. Returns None for empty / whitespace-only input.
    """
    if not raw_html:
        return None

    text = html.unescape(raw_html)
    # Remove script/style *bodies* before stripping tags, so their contents
    # don't leak into the prompt as if they were posting text.
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    if not text:
        return None

    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    # Prefer a word boundary, but if a single token exceeds max_chars just
    # hard-cut so we always make progress.
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip() + " …"
