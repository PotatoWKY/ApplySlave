"""Protocol (interface) definitions shared across packages.

Using `typing.Protocol` for structural typing: any class that implements the
expected methods satisfies the protocol without needing to inherit from it.
This keeps package boundaries clean without circular imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from hamster.shared.models import (
    ApplyResult,
    FillPlan,
    JobListing,
    PageAnalysis,
    PageDOM,
    SearchQuery,
    UserProfile,
)


@runtime_checkable
class JobSource(Protocol):
    """Any ATS or job board that can return job listings."""

    name: str

    async def list_jobs(self, query: SearchQuery) -> list[JobListing]:
        """Return listings matching the query. May hit network."""
        ...


@runtime_checkable
class ProfileStorage(Protocol):
    """Persistence for the single user profile and resume files."""

    def save_profile(self, profile: UserProfile) -> UserProfile:
        """Insert or update the profile, returning the stored version with id."""
        ...

    def load_profile(self) -> UserProfile | None:
        """Return the current profile, or None if not configured."""
        ...

    def save_resume_file(self, source: Path, name: str) -> Path:
        """Copy a resume into managed storage. Returns the stored path."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Local LLM used for page understanding and field mapping."""

    async def chat_json(self, prompt: str, schema: dict | None = None) -> dict:
        """Generate a JSON response. May enforce schema at decode time."""
        ...


@runtime_checkable
class PromptBuilder(Protocol):
    """Assembles prompts for specific LLM tasks."""

    def build_page_analysis_prompt(self, dom: PageDOM) -> str: ...

    def build_form_mapping_prompt(
        self,
        dom: PageDOM,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> str: ...


@runtime_checkable
class PageAnalyzer(Protocol):
    async def analyze(self, dom: PageDOM) -> PageAnalysis: ...


@runtime_checkable
class FormMapper(Protocol):
    # job is optional so manual-URL applications (no JobListing) and the
    # deterministic path keep working; it only feeds the LLM free-text pass.
    async def plan(
        self,
        dom: PageDOM,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> FillPlan: ...


@runtime_checkable
class Applicator(Protocol):
    """High-level entry point: given a URL and profile, attempt to apply."""

    async def apply(
        self,
        url: str,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> ApplyResult: ...
