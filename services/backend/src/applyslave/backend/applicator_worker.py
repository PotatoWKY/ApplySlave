"""Background worker that consumes queued applications.

Polls the applications table for status=queued, runs the ApplicatorEngine
against each, and updates status to submitted / failed / needs_review.

The worker uses a single shared BrowserManager (Chromium with persistent
context) so cookies / sessions accumulate across applications. This is
fine because every external apply URL is an independent context anyway.

Designed to be cancellable: if the FastAPI lifespan context exits we
cancel the worker task and clean up the browser.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from applyslave.applicator import ApplicatorEngine
from applyslave.applicator.browser import BrowserManager
from applyslave.backend.dependencies import (
    get_data_dir,
    get_jsearch_api_key,  # noqa: F401  (kept for symmetry)
    get_profile_store,
    get_result_logger,
    is_dry_run_enabled,
)
from applyslave.shared import ApplicationStatus

logger = logging.getLogger(__name__)


_POLL_INTERVAL_SECONDS = 3.0


class ApplicatorWorker:
    """Background loop that processes queued applications."""

    def __init__(self, ws_hub) -> None:
        self._ws_hub = ws_hub
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._browser: BrowserManager | None = None
        self._engine: ApplicatorEngine | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="applicator-worker")
        logger.info("Applicator worker started")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to close browser")
            self._browser = None
            self._engine = None
        logger.info("Applicator worker stopped")

    async def _loop(self) -> None:
        result_logger = get_result_logger()
        profile_store = get_profile_store()

        while not self._stop_event.is_set():
            queued = result_logger.list_applications(
                status=ApplicationStatus.QUEUED, limit=1
            )
            if not queued:
                await self._sleep_or_stop(_POLL_INTERVAL_SECONDS)
                continue

            record = queued[0]
            profile = profile_store.load_profile()
            if profile is None:
                logger.warning(
                    "No profile saved; cannot apply to %s. Skipping.",
                    record.url,
                )
                if record.id is not None:
                    result_logger.update_status(
                        record.id,
                        status=ApplicationStatus.FAILED,
                        error="No profile saved",
                    )
                await self._sleep_or_stop(_POLL_INTERVAL_SECONDS)
                continue

            await self._process(record, profile, result_logger)

    async def _process(self, record, profile, result_logger) -> None:
        record_id = record.id
        url = record.url
        logger.info("Applying to %s (%s)", url, record.title)

        if record_id is not None:
            result_logger.update_status(
                record_id, status=ApplicationStatus.IN_PROGRESS
            )
        await self._broadcast(
            {
                "type": "apply_started",
                "application_id": record_id,
                "url": url,
            }
        )

        engine = await self._ensure_engine()

        try:
            result = await engine.apply(url, profile)
        except Exception as error:  # noqa: BLE001
            logger.exception("Engine crashed for %s", url)
            result = None
            if record_id is not None:
                result_logger.update_status(
                    record_id,
                    status=ApplicationStatus.FAILED,
                    error=f"engine crashed: {error}",
                )
            await self._broadcast(
                {
                    "type": "apply_failed",
                    "application_id": record_id,
                    "url": url,
                    "error": str(error),
                }
            )
            return

        if record_id is not None:
            result_logger.update_status(
                record_id,
                status=result.status,
                error=result.error,
                applied_at=datetime.now(UTC)
                if result.status is ApplicationStatus.SUBMITTED
                else None,
            )

        await self._broadcast(
            {
                "type": "apply_finished",
                "application_id": record_id,
                "url": url,
                "status": result.status.value,
                "intervention_reason": result.intervention_reason,
                "error": result.error,
            }
        )
        logger.info(
            "Apply for %s finished: %s%s",
            url,
            result.status.value,
            f" ({result.intervention_reason})" if result.intervention_reason else "",
        )

    async def _ensure_engine(self) -> ApplicatorEngine:
        if self._engine is not None:
            return self._engine

        data_dir = get_data_dir()
        browser = BrowserManager(
            user_data_dir=data_dir / "browser_profile",
            headless=True,
        )
        await browser.launch()
        self._browser = browser

        screenshots = data_dir / "screenshots"
        self._engine = ApplicatorEngine(
            browser=browser,
            dry_run=is_dry_run_enabled(),
            screenshot_dir=screenshots,
        )
        return self._engine

    async def _broadcast(self, message: dict) -> None:
        try:
            await self._ws_hub.broadcast(message)
        except Exception:  # noqa: BLE001
            logger.exception("WebSocket broadcast failed")

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
