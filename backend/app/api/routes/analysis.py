"""
Analysis router for Lumenis AI.

Provides CRUD-style endpoints for analysis jobs and their reports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.api.deps import get_db, get_valid_job
from app.core.config import settings
from app.models.job import Job
from app.models.report import Report
from app.schemas.job import JobList, JobResponse
from app.schemas.report import FullReport

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


# ── List jobs with pagination ────────────────────────────────────────
@router.get(
    "/jobs",
    response_model=JobList,
    summary="List analysis jobs",
)
async def list_jobs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
) -> JobList:
    """Return a paginated list of analysis jobs ordered by creation date (newest first)."""
    # Total count
    count_result = await db.execute(select(func.count()).select_from(Job))
    total = count_result.scalar_one()

    # Paginated results
    result = await db.execute(
        select(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    )
    jobs = result.scalars().all()

    return JobList(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        skip=skip,
        limit=limit,
    )


# ── Get single job ──────────────────────────────────────────────────
@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get a single analysis job",
)
async def get_job(
    job: Job = Depends(get_valid_job),
) -> JobResponse:
    """Return full details for a single analysis job."""
    return JobResponse.model_validate(job)


# ── Get job file ────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}/file",
    summary="Get the uploaded file for a job",
)
async def get_job_file(
    job: Job = Depends(get_valid_job),
):
    """Return the original uploaded file for a job."""
    if not job.file_path:
        raise HTTPException(status_code=404, detail="File path not found in job record")
        
    file_path = Path(job.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"
        
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=job.original_filename,  # Fixed: was job.file_name which does not exist
    )


# ── Stream job status (SSE) ─────────────────────────────────────────

@router.get(
    "/jobs/{job_id}/stream",
    summary="Stream real-time analysis status via SSE",
)
async def stream_job_status(
    job: Job = Depends(get_valid_job),
):
    """
    Stream real-time status updates using Server-Sent Events (SSE).
    Subscribes to a Redis channel for the specific job.
    """
    async def event_generator():
        # If already completed or failed, send the final state immediately
        if job.status in ("completed", "failed"):
            yield f"data: {{\"step\": 6, \"message\": \"Analysis {job.status}.\", \"status\": \"{job.status}\"}}\n\n"
            return

        r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        pubsub = r.pubsub()
        channel = f"job:{job.id}:status"
        await pubsub.subscribe(channel)
        
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    # Try to parse the json to see if it's the terminal step
                    try:
                        parsed = json.loads(data)
                        if parsed.get("step") == 6 or parsed.get("step") == -1:
                            break
                    except Exception:
                        pass
                else:
                    # Keep-alive heartbeat
                    yield ": heartbeat\n\n"
                
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected for job {job.id}")
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Delete job ──────────────────────────────────────────────────────
@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete an analysis job",
)
async def delete_job(
    job: Job = Depends(get_valid_job),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an analysis job and its associated file from disk.

    If the file no longer exists on disk the job record is still removed.
    """
    # ── Remove file from disk ────────────────────────────────────────
    if job.file_path:
        file_path = Path(job.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info("Deleted file %s for job %s", file_path, job.id)
            except OSError as exc:
                logger.warning(
                    "Could not delete file %s for job %s: %s",
                    file_path,
                    job.id,
                    exc,
                )

    # ── Remove associated report(s) ─────────────────────────────────
    await db.execute(delete(Report).where(Report.job_id == job.id))

    # ── Remove job record ────────────────────────────────────────────
    await db.delete(job)
    await db.flush()
    logger.info("Deleted job %s", job.id)


# ── Get report for a completed job ──────────────────────────────────
@router.get(
    "/jobs/{job_id}/report",
    response_model=FullReport,
    summary="Get the analysis report for a job",
)
async def get_job_report(
    job: Job = Depends(get_valid_job),
    db: AsyncSession = Depends(get_db),
) -> FullReport:
    """
    Return the full analysis report for a completed job.

    Raises:
        HTTPException 400: If the job has not completed yet.
        HTTPException 404: If no report exists for the job.
    """
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Report is only available for completed jobs. "
                f"Current status: '{job.status}'."
            ),
        )

    result = await db.execute(select(Report).where(Report.job_id == job.id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report found for job '{job.id}'.",
        )

    return FullReport.model_validate(report)
