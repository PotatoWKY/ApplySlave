"""Download the default local LLM into the user data dir.

Usage: uv run python scripts/download_model.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from applyslave.applicator.llm import ModelManager


DATA_DIR = Path.home() / "Library" / "Application Support" / "ApplySlave"


async def main() -> None:
    manager = ModelManager(data_dir=DATA_DIR)
    if manager.is_installed():
        print(f"Already installed at {manager.model_path}")
        return

    last_print = [time.monotonic()]
    print(f"Downloading {manager.model_name} to {manager.model_path}")

    def report(downloaded: int, total: int | None) -> None:
        now = time.monotonic()
        if now - last_print[0] < 2.0 and downloaded != total:
            return
        last_print[0] = now
        mb = downloaded / (1024 * 1024)
        if total:
            total_mb = total / (1024 * 1024)
            pct = downloaded / total * 100
            sys.stdout.write(
                f"\r{mb:.1f} / {total_mb:.1f} MB  ({pct:.1f}%)"
            )
        else:
            sys.stdout.write(f"\r{mb:.1f} MB")
        sys.stdout.flush()

    path = await manager.download(progress=report)
    sys.stdout.write("\n")
    print(f"Saved to {path}")


if __name__ == "__main__":
    asyncio.run(main())
