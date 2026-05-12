"""Local LLM client wrapping llama-cpp-python.

Kept thin so the rest of the code depends only on the ``chat_json`` shape
(not on llama-cpp's API). This also makes it trivial to swap in a mock for
tests or a different backend later.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LLMClient:
    """Load a GGUF model on demand and ask it for JSON responses."""

    def __init__(
        self,
        *,
        model_path: Path,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,
        verbose: bool = False,
    ) -> None:
        self._model_path = Path(model_path)
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._verbose = verbose
        self._llama: Any | None = None  # lazy init

    def _ensure_loaded(self) -> None:
        if self._llama is not None:
            return
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {self._model_path}. "
                "Call ModelManager.download() first."
            )
        # Import inside the method so we don't pay the C++ init cost until use.
        from llama_cpp import Llama

        logger.info("Loading LLM from %s", self._model_path)
        self._llama = Llama(
            model_path=str(self._model_path),
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=self._verbose,
        )

    async def chat_json(
        self, prompt: str, schema: dict | None = None
    ) -> dict:
        """Ask the model for a JSON response to ``prompt``.

        If ``schema`` is provided it is passed to llama.cpp's grammar-based
        constrained decoding so the output is guaranteed to validate.
        """
        import asyncio

        self._ensure_loaded()
        assert self._llama is not None

        def _run() -> str:
            kwargs: dict[str, Any] = {
                "max_tokens": 1024,
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
                if schema is None
                else {"type": "json_object", "schema": schema},
            }
            completion = self._llama.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            return completion["choices"][0]["message"]["content"]

        raw = await asyncio.to_thread(_run)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"LLM returned non-JSON response: {raw!r}"
            ) from error


class StaticLLMClient:
    """Test / placeholder client that returns a pre-canned dict.

    Satisfies the ``LLMClient`` protocol for offline tests and for stubbing
    out the LLM path before the model is downloaded.
    """

    def __init__(self, response: dict) -> None:
        self._response = response

    async def chat_json(
        self, prompt: str, schema: dict | None = None
    ) -> dict:
        del prompt, schema
        return dict(self._response)
