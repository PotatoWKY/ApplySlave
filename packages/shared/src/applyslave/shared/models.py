"""Core data models shared across all ApplySlave packages.

These are Pydantic models so they:
- Serialize cleanly to / from JSON for the FastAPI layer.
- Validate at the boundary between packages.
- Auto-generate OpenAPI schemas for the frontend.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class _StrictModel(BaseModel):
    """Base class that forbids extra fields and normalizes naming."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


# --- User profile -----------------------------------------------------------


class Education(_StrictModel):
    school: str
    degree: str | None = None
    major: str | None = None
    start_date: str | None = None  # "YYYY-MM"
    end_date: str | None = None


class Experience(_StrictModel):
    company: str
    title: str
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None  # None = current role


class UserProfile(_StrictModel):
    """Everything we know about the user. Persisted in SQLite."""

    id: int | None = None
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    resume_path: str | None = None
    updated_at: datetime | None = None


# --- Job discovery ----------------------------------------------------------


class JobSourceName(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKABLE = "workable"
    LINKEDIN = "linkedin"


class JobListing(_StrictModel):
    """A single job returned by a JobSource."""

    id: str
    source: JobSourceName
    company: str
    title: str
    location: str | None = None
    url: HttpUrl
    apply_url: HttpUrl | None = None
    description_snippet: str | None = None
    posted_at: datetime | None = None
    remote: bool = False


class SearchQuery(_StrictModel):
    """Filter parameters for job discovery."""

    keywords: str = ""
    location: str = ""
    remote_only: bool = False
    experience_levels: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    max_results: int = 200


# --- Application execution --------------------------------------------------


class ActionType(str, Enum):
    FILL = "fill"
    CLICK = "click"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    UPLOAD = "upload"


class PageAction(_StrictModel):
    """An atomic action the browser layer can execute."""

    type: ActionType
    selector: str
    value: str | None = None


class ApplicationStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"  # low-confidence / CAPTCHA


class ApplicationRecord(_StrictModel):
    """Persisted row in the applications table."""

    id: int | None = None
    url: str
    company: str
    title: str
    status: ApplicationStatus = ApplicationStatus.QUEUED
    error: str | None = None
    applied_at: datetime | None = None
    created_at: datetime | None = None


class ApplyResult(_StrictModel):
    """Result returned by the applicator after attempting one job."""

    success: bool
    status: ApplicationStatus
    url: str
    company: str | None = None
    title: str | None = None
    error: str | None = None
    confidence: float = 1.0  # LLM-reported confidence
    intervention_reason: str | None = None  # if needs_review


# --- Page structure (DOM extraction output) ---------------------------------


class ElementType(str, Enum):
    INPUT_TEXT = "input_text"
    INPUT_EMAIL = "input_email"
    INPUT_TEL = "input_tel"
    INPUT_PASSWORD = "input_password"
    INPUT_FILE = "input_file"
    INPUT_CHECKBOX = "input_checkbox"
    INPUT_RADIO = "input_radio"
    SELECT = "select"
    TEXTAREA = "textarea"
    BUTTON = "button"
    OTHER = "other"


class PageElement(_StrictModel):
    """One interactable element on a page, as captured by DOMExtractor."""

    id: str  # internal "el_1", "el_2"...
    element_type: ElementType
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    options: list[str] = Field(default_factory=list)  # for select / radio groups
    current_value: str | None = None
    selector: str  # CSS selector the browser layer can use


class PageDOM(_StrictModel):
    """Structured snapshot of a page, consumed by FormFiller."""

    url: str
    title: str
    elements: list[PageElement] = Field(default_factory=list)


class PageType(str, Enum):
    LOGIN = "login"
    JOB_LIST = "job_list"
    JOB_DETAIL = "job_detail"
    APPLICATION_FORM = "application_form"
    CONFIRMATION = "confirmation"
    CAPTCHA = "captcha"
    UNKNOWN = "unknown"


class PageAnalysis(_StrictModel):
    """Output from PageAnalyzer."""

    page_type: PageType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None


class FillPlan(_StrictModel):
    """Output from FormMapper → consumed by ActionExecutor."""

    actions: list[PageAction] = Field(default_factory=list)
    unmapped_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    reasoning: str | None = None
