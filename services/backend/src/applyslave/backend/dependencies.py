"""Shared singletons + DI helpers for the FastAPI layer.

Keeping construction centralized so tests can swap them via
``app.dependency_overrides`` cleanly.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from applyslave.orchestrator import ResultLogger
from applyslave.profile_store import ProfileStore


def get_data_dir() -> Path:
    """Where everything the backend persists lives.

    Order of precedence:
      1. APPLYSLAVE_DATA_DIR env var (Tauri passes this at startup)
      2. ~/Library/Application Support/ApplySlave on macOS
      3. ~/.config/ApplySlave on Linux/other
    """
    explicit = os.environ.get("APPLYSLAVE_DATA_DIR")
    if explicit:
        return Path(explicit)
    home = Path.home()
    if (home / "Library" / "Application Support").exists():
        return home / "Library" / "Application Support" / "ApplySlave"
    return home / ".config" / "ApplySlave"


@lru_cache(maxsize=1)
def get_profile_store() -> ProfileStore:
    return ProfileStore(get_data_dir())


@lru_cache(maxsize=1)
def get_result_logger() -> ResultLogger:
    return ResultLogger(get_data_dir())
