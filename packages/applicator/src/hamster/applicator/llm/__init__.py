"""Local LLM via llama-cpp-python, with model download and prompt building."""

from hamster.applicator.llm.client import LLMClient, StaticLLMClient
from hamster.applicator.llm.level_recommender import (
    VALID_LEVELS,
    LevelRecommendation,
    LevelRecommender,
)
from hamster.applicator.llm.model_manager import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_URL,
    ModelManager,
)
from hamster.applicator.llm.prompt_builder import DefaultPromptBuilder
from hamster.applicator.llm.resume_extractor import ResumeExtractor

__all__ = [
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_URL",
    "DefaultPromptBuilder",
    "LLMClient",
    "LevelRecommendation",
    "LevelRecommender",
    "ModelManager",
    "ResumeExtractor",
    "StaticLLMClient",
    "VALID_LEVELS",
]
