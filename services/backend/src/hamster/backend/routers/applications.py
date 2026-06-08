"""Application submission + listing endpoints."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from hamster.backend.dependencies import get_result_logger
from hamster.orchestrator import ResultLogger
from hamster.shared import ApplicationRecord, ApplicationStatus, JobListing
from pydantic import BaseModel

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


class SubmitUrlRequest(BaseModel):
    """A single application URL the user pasted in manually."""

    url: str


class SubmitUrlResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    application: ApplicationRecord | None = None


def _company_from_url(url: str) -> str:
    """Best-effort company label from a URL host (e.g. 'boards.greenhouse.io')."""
    host = urlparse(url).netloc
    return host or "Unknown"


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
    """Queue a batch of jobs for the apply pipeline.

    Inserts each job as a QUEUED application. The ApplicatorWorker started in
    the app lifespan (see ``main.py``) polls for QUEUED rows and runs the
    browser + LLM pipeline automatically — gated to dry-run by default, so it
    fills the form and screenshots it without clicking submit unless the user
    disables dry-run in Settings.
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


@router.post(
    "/url",
    response_model=SubmitUrlResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_url(
    payload: SubmitUrlRequest,
    result_logger: Annotated[ResultLogger, Depends(get_result_logger)],
) -> SubmitUrlResponse:
    """Queue a single application URL the user pasted in by hand.

    Goes into the same applications table the worker polls — there is one
    queue, whether a job came from Discovery or was added manually. We don't
    have a JobListing for a hand-entered URL, so company/title start as
    placeholders; the engine fills the form from the page itself.
    """
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="url must not be empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=422, detail="url must be an absolute http(s) URL"
        )

    existing = result_logger.get_by_url(url)
    if existing is not None and existing.status in {
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.SUBMITTED,
    }:
        return SubmitUrlResponse(
            accepted=False,
            reason=f"already {existing.status.value}",
            application=existing,
        )

    record = result_logger.insert_application(
        ApplicationRecord(
            url=url,
            company=_company_from_url(url),
            title="Manual application",
            status=ApplicationStatus.QUEUED,
        )
    )
    return SubmitUrlResponse(accepted=True, application=record)
