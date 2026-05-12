"""Shared data models and protocols used across ApplySlave packages."""

from applyslave.shared.models import (
    ActionType,
    ApplicationRecord,
    ApplicationStatus,
    ApplyResult,
    Education,
    ElementType,
    Experience,
    FillPlan,
    JobListing,
    JobSourceName,
    PageAction,
    PageAnalysis,
    PageDOM,
    PageElement,
    PageType,
    SearchQuery,
    UserProfile,
)
from applyslave.shared.protocols import (
    Applicator,
    FormMapper,
    JobSource,
    LLMClient,
    PageAnalyzer,
    ProfileStorage,
    PromptBuilder,
)

__all__ = [
    # models
    "ActionType",
    "ApplicationRecord",
    "ApplicationStatus",
    "ApplyResult",
    "Education",
    "ElementType",
    "Experience",
    "FillPlan",
    "JobListing",
    "JobSourceName",
    "PageAction",
    "PageAnalysis",
    "PageDOM",
    "PageElement",
    "PageType",
    "SearchQuery",
    "UserProfile",
    # protocols
    "Applicator",
    "FormMapper",
    "JobSource",
    "LLMClient",
    "PageAnalyzer",
    "ProfileStorage",
    "PromptBuilder",
]
