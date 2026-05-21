"""
API dependency functions for Lumenis AI.

Provides reusable FastAPI dependencies for database sessions,
job validation, and file upload validation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Path, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

# Re-export so routes can do: from app.api.deps import get_db
get_db = get_db

# Supported MIME types for medical image uploads
ALLOWED_CONTENT_TYPES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/dicom",
    "application/dicom",
    "application/pdf",
}


async def get_valid_job(
    job_id: Annotated[uuid.UUID, Path(description="The UUID of the analysis job")],
    db: AsyncSession = Depends(get_db),
):
    """
    Path dependency that fetches a job by its UUID.

    Raises:
        HTTPException 404: If no job with the given ID exists.
    """
    from app.models.job import Job

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found.",
        )
    return job


async def validate_file_upload(file: UploadFile) -> UploadFile:
    """
    Validates an uploaded file against allowed MIME types and max size.

    Checks:
        1. Content-Type is in the allowed set.
        2. File size does not exceed settings.MAX_FILE_SIZE_MB.

    Raises:
        HTTPException 415: If the file type is not supported.
        HTTPException 413: If the file exceeds the maximum size.

    Returns:
        The validated UploadFile (unchanged).
    """
    # ── Validate content type ────────────────────────────────────────
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type: '{file.content_type}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )

    # ── Validate file size ───────────────────────────────────────────
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(contents) / (1024 * 1024):.1f} MB) exceeds "
                f"maximum allowed size ({settings.MAX_FILE_SIZE_MB} MB)."
            ),
        )

    # Reset the file cursor so downstream consumers can read it again
    await file.seek(0)
    return file
