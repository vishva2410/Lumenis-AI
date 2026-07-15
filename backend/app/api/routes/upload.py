"""
Upload router for Lumenis AI.

Handles medical image file uploads: validates the file, persists it
to disk with a collision-safe UUID filename, creates a Job record,
and dispatches the asynchronous analysis Celery task.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_limiter.depends import RateLimiter

from app.api.deps import get_db, validate_file_upload
from app.core.config import settings
from app.models.job import Job
from app.schemas.job import JobResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])


def _build_safe_filename(original_filename: str) -> str:
    """Generate a UUID-prefixed filename preserving the original extension."""
    ext = Path(original_filename or "upload").suffix or ".bin"
    return f"{uuid.uuid4().hex}{ext}"


@router.post(
    "/upload",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a medical image for analysis",
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def upload_file(
    file: UploadFile = Depends(validate_file_upload),
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Upload a medical image and queue it for analysis.

    Steps:
        1. Generate a collision-safe filename.
        2. Write the file to ``settings.UPLOAD_DIR``.
        3. Create a ``Job`` record with status *pending*.
        4. Dispatch the Celery analysis task.
        5. Return 202 Accepted with the job metadata.
    """
    # ── 1. Prepare destination path ──────────────────────────────────
    safe_name = _build_safe_filename(file.filename)
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / safe_name

    # ── 2. Persist file to disk ──────────────────────────────────────
    try:
        async with aiofiles.open(dest_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                await out.write(chunk)
        logger.info("Saved upload to %s (%s)", dest_path, file.content_type)
    except Exception as exc:
        logger.error("Failed to save uploaded file: %s", exc)
        # Clean up partial writes
        if dest_path.exists():
            dest_path.unlink()
        raise

    # ── 3. Create Job record ─────────────────────────────────────────
    job = Job(
        original_filename=file.filename,
        file_path=str(dest_path),
        file_type=file.content_type,
        status="pending",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.info("Created job %s for file %s", job.id, safe_name)

    # ── 4. Dispatch Celery task ──────────────────────────────────────
    try:
        from app.workers.analysis_task import run_analysis

        run_analysis.delay(str(job.id), str(dest_path))
        logger.info("Dispatched analysis task for job %s", job.id)
    except Exception as exc:
        # If task dispatch fails, mark the job as failed but don't crash
        logger.error("Failed to dispatch Celery task for job %s: %s", job.id, exc)
        job.status = "failed"
        job.error_message = f"Task dispatch failed: {exc}"
        await db.flush()

    # ── 5. Commit and return response ────────────────────────────────
    await db.commit()
    return JobResponse.model_validate(job)
