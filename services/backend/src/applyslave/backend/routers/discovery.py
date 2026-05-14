"""Job-discovery endpoints.

The search itself runs asynchronously in a background task so the HTTP
call returns quickly with a task_id. Progress is pushed over WebSocket;
the final result is also persisted to SQLite so the client can fetch it
later by task_id even if the WebSocket disconnected.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from applyslave.backend.dependencies import get_jsearch_api_key, get_profile_store, get_result_logger
from applyslave.job_discovery import build_default_aggregator
from applyslave.job_discovery.relevance import score_job
from applyslave.orchestrator import ResultLogger
from applyslave.profile_store import ProfileStore
from applyslave.shared import JobListing, SearchQuery

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["discovery"])


class DiscoverRequest(BaseModel):
    keywords: str = ""
    location: str = ""
    remote_only: bool = False
    exclude_companies: list[str] = []
    max_results: int = 200
    sources: list[str] | None = None  # reserved for future filtering


class DiscoverResponse(BaseModel):
    task_id: str
    status: str


class DiscoveryTaskDetail(BaseModel):
    task_id: str
    status: str
    results: list[JobListing] | None = None


@router.post(
    "/discover",
    response_model=DiscoverResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_discovery(
    payload: DiscoverRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
) -> DiscoverResponse:
    task_id = f"disc-{uuid.uuid4().hex[:12]}"

    result_logger.save_discovery_task(
        task_id=task_id,
        keywords=payload.keywords,
        location=payload.location,
        filters=payload.model_dump(),
        status="queued",
    )

    background_tasks.add_task(
        _run_discovery,
        task_id,
        payload,
        result_logger,
        request.app.state.ws_hub,
    )
    return DiscoverResponse(task_id=task_id, status="queued")


@router.get("/discover/{task_id}")
async def get_discovery_task(
    task_id: str,
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
    profile_store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> dict:
    raw = result_logger.load_discovery_task(task_id)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_id}")

    results = None
    if raw.get("results"):
        jobs = [JobListing.model_validate(item) for item in raw["results"]]
        profile = profile_store.load_profile()

        results = []
        for job in jobs:
            job_dict = job.model_dump(mode="json")
            if profile:
                job_dict["relevance_score"] = score_job(job, profile)
            else:
                job_dict["relevance_score"] = 50
            results.append(job_dict)

    return {
        "task_id": raw["id"],
        "status": raw["status"],
        "results": results,
    }


async def _run_discovery(
    task_id: str,
    payload: DiscoverRequest,
    result_logger: ResultLogger,
    ws_hub,
) -> None:
    query = SearchQuery(
        keywords=payload.keywords,
        location=payload.location,
        remote_only=payload.remote_only,
        exclude_companies=payload.exclude_companies,
        max_results=payload.max_results,
    )
    result_logger.save_discovery_task(
        task_id=task_id,
        keywords=payload.keywords,
        location=payload.location,
        filters=payload.model_dump(),
        status="running",
    )
    await ws_hub.broadcast(
        {"type": "discovery_started", "task_id": task_id}
    )

    aggregator, sources = build_default_aggregator(jsearch_api_key=get_jsearch_api_key())
    try:
        jobs = await aggregator.discover(query)
    except Exception as error:  # noqa: BLE001
        logger.exception("Discovery failed")
        result_logger.save_discovery_task(
            task_id=task_id,
            keywords=payload.keywords,
            location=payload.location,
            filters=payload.model_dump(),
            status="failed",
        )
        await ws_hub.broadcast(
            {"type": "discovery_failed", "task_id": task_id, "error": str(error)}
        )
        return
    finally:
        # Ensure httpx clients close even if discovery raised
        await asyncio.gather(
            *(source.aclose() for source in sources), return_exceptions=True
        )

    results_payload = [job.model_dump(mode="json") for job in jobs]
    result_logger.save_discovery_task(
        task_id=task_id,
        keywords=payload.keywords,
        location=payload.location,
        filters=payload.model_dump(),
        status="completed",
        results=results_payload,
    )
    await ws_hub.broadcast(
        {
            "type": "discovery_completed",
            "task_id": task_id,
            "total_jobs": len(jobs),
        }
    )
