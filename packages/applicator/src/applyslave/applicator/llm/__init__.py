"""Local LLM via llama-cpp-python, with model download and prompt building."""

from applyslave.applicator.llm.client import LLMClient, StaticLLMClient
from applyslave.applicator.llm.model_manager import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_URL,
    ModelManager,
)
from applyslave.applicator.llm.prompt_builder import DefaultPromptBuilder
from applyslave.applicator.llm.resume_extractor import ResumeExtractor

__all__ = [
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_URL",
    "DefaultPromptBuilder",
    "LLMClient",
    "ModelManager",
    "ResumeExtractor",
    "StaticLLMClient",
]
