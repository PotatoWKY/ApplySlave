"""PDF resume parser.

First pass uses regex + heuristics on text extracted with pdfplumber. This
covers most machine-generated resumes (LaTeX, Word). When that fails, the
caller can fall back to an LLM-based extraction (implemented later in the
applicator/llm package) — this module stays dependency-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
# Accepts +country prefix, parentheses, dashes, spaces; at least 7 digits.
PHONE_RE = re.compile(
    r"""
    (?:\+\d{1,3}[\s-]?)?      # optional country prefix
    (?:\(\d{1,4}\)[\s-]?)?    # optional area code in parens
    \d{3,4}[\s-]?\d{3,4}       # mandatory groups
    (?:[\s-]?\d{0,4})?         # optional trailing
    """,
    re.VERBOSE,
)
LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-%]+/?", re.IGNORECASE
)
GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.IGNORECASE
)


@dataclass
class ParsedResume:
    """Fields extracted from a resume PDF via regex + heuristics."""

    full_text: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None


def extract_text(pdf_path: Path) -> str:
    """Read a PDF and return all text as a single string."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    pages: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n".join(pages)


def _find_name(text: str) -> tuple[str | None, str | None]:
    """Very simple name heuristic: first non-empty line, two+ words of letters."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip lines that look like contact info
        if EMAIL_RE.search(line) or "http" in line.lower() or "@" in line:
            continue
        parts = line.split()
        if 2 <= len(parts) <= 5 and all(_looks_like_name_token(p) for p in parts):
            first = parts[0]
            last = parts[-1]
            return first, last
    return None, None


_NAME_TOKEN_RE = re.compile(r"^[A-Z][a-zA-Z'\-\.]{1,}$")


def _looks_like_name_token(token: str) -> bool:
    return bool(_NAME_TOKEN_RE.match(token))


def parse_resume(pdf_path: Path) -> ParsedResume:
    """Extract what we can from a resume PDF. Any field may be None."""
    text = extract_text(pdf_path)

    first, last = _find_name(text)

    email_match = EMAIL_RE.search(text)

    phone: str | None = None
    for match in PHONE_RE.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:
            phone = candidate
            break

    linkedin_match = LINKEDIN_RE.search(text)
    github_match = GITHUB_RE.search(text)

    def _normalize_url(url: str | None) -> str | None:
        if url is None:
            return None
        url = url.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    return ParsedResume(
        full_text=text,
        first_name=first,
        last_name=last,
        email=email_match.group(0) if email_match else None,
        phone=phone,
        linkedin_url=_normalize_url(linkedin_match.group(0) if linkedin_match else None),
        github_url=_normalize_url(github_match.group(0) if github_match else None),
    )
