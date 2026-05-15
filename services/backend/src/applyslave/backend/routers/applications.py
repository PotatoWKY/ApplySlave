"""Application submission + listing endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from applyslave.backend.dependencies import get_result_logger
from applyslave.orchestrator import ResultLogger
from applyslave.shared import ApplicationRecord, ApplicationStatus, JobListing

router = APIRouter(prefix="/api/applications", tags=["applications"])


class ApplicationsListResponse(BaseModel):
    total: int
    applications: list[ApplicationRecord]


class SubmitBatchRequest(BaseModel):
    """Accepts the full JobListing so we can store it for later display."""

    jobs: list[JobListing]


class SubmitBatchResponse(BaseModel):
    accepted: int
    skipped_duplicates: int


@router.get("", response_model=ApplicationsListResponse)
async def list_applications(
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    limit: int = 100,
    offset: int = 0,
) -> ApplicationsListResponse:
    records = result_logger.list_applications(
        status=status_filter, limit=limit, offset=offset
    )
    return ApplicationsListResponse(total=len(records), applications=records)


@router.get("/{application_id}", response_model=ApplicationRecord)
async def get_application(
    application_id: int,
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
) -> ApplicationRecord:
    # Single-row lookup via listing fallback (our logger uses URL as the
    # natural key). For now expose via list to avoid re-implementing here.
    records = result_logger.list_applications(limit=1_000_000)
    for record in records:
        if record.id == application_id:
            return record
    raise HTTPException(status_code=404, detail="application not found")


@router.post("", response_model=SubmitBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_batch(
    payload: SubmitBatchRequest,
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
) -> SubmitBatchResponse:
    """Queue a batch of jobs for later processing.

    For now, actually running the browser + LLM pipeline is opt-in and
    requires a separate worker (or the model download). This endpoint just
    records the intent so the UI has something to display.
    """
    accepted = 0
    skipped = 0
    for job in payload.jobs:
        url_str = str(job.apply_url or job.url)
        existing = result_logger.get_by_url(url_str)
        if existing is not None and existing.status in {
            ApplicationStatus.IN_PROGRESS,
            ApplicationStatus.SUBMITTED,
        }:
            skipped += 1
            continue
        result_logger.insert_application(
            ApplicationRecord(
                url=url_str,
                company=job.company,
                title=job.title,
                status=ApplicationStatus.QUEUED,
                job=job,
            )
        )
        accepted += 1
    return SubmitBatchResponse(accepted=accepted, skipped_duplicates=skipped)
