"""Shared singletons + DI helpers for the FastAPI layer.

Keeping construction centralized so tests can swap them via
``app.dependency_overrides`` cleanly.
"""

from __future__ import annotations

import json
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


def _settings_path() -> Path:
    return get_data_dir() / "settings.json"


def load_settings() -> dict:
    """Load user settings from disk. Returns empty dict if not found."""
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict) -> None:
    """Persist user settings to disk."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get_jsearch_api_key() -> str | None:
    """Return the JSearch API key if configured, else None."""
    return load_settings().get("jsearch_api_key") or None


def is_dry_run_enabled() -> bool:
    """Read the dry_run flag. Defaults to True (safe)."""
    settings = load_settings()
    if "dry_run" not in settings:
        return True
    return bool(settings["dry_run"])


@lru_cache(maxsize=1)
def get_profile_store() -> ProfileStore:
    return ProfileStore(get_data_dir())


@lru_cache(maxsize=1)
def get_result_logger() -> ResultLogger:
    return ResultLogger(get_data_dir())
