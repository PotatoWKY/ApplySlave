"""Download and locate the local LLM model file.

We intentionally do not bundle the model (4+ GB) with the app. Instead, we
download on first run into the user's data directory. This module encapsulates
that so the rest of the code can just ask "where's the model?".
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


DEFAULT_MODEL_NAME = "qwen3-4b-instruct-2507-q4_k_m"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/"
    "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
)


ProgressCallback = Callable[[int, int | None], None]


class ModelManager:
    """Manages the on-disk LLM model files under a data directory."""

    def __init__(
        self,
        *,
        data_dir: Path,
        model_name: str = DEFAULT_MODEL_NAME,
        url: str = DEFAULT_MODEL_URL,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._models_dir = self._data_dir / "models"
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._model_name = model_name
        self._url = url

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_path(self) -> Path:
        return self._models_dir / f"{self._model_name}.gguf"

    def is_installed(self) -> bool:
        return self.model_path.exists() and self.model_path.stat().st_size > 0

    async def download(self, progress: ProgressCallback | None = None) -> Path:
        """Stream the model to disk, optionally reporting progress."""
        if self.is_installed():
            logger.info("Model %s already present at %s", self._model_name, self.model_path)
            return self.model_path

        tmp_path = self.model_path.with_suffix(".gguf.part")
        logger.info("Downloading %s from %s", self._model_name, self._url)
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", self._url) as response:
                response.raise_for_status()
                total_str = response.headers.get("content-length")
                total = int(total_str) if total_str else None
                downloaded = 0
                with tmp_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress is not None:
                            progress(downloaded, total)
        os.replace(tmp_path, self.model_path)
        logger.info("Model downloaded to %s", self.model_path)
        return self.model_path
