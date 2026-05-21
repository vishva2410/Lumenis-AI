"""
Lumenis AI — Job Schemas

Pydantic models for job creation, status tracking, and list responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Schema for creating a new analysis job (file metadata only)."""

    file_name: str = Field(
        ...,
        max_length=512,
        description="Original file name as uploaded by the client",
        examples=["chest_xray_001.dcm"],
    )
    file_type: str = Field(
        ...,
        max_length=128,
        description="MIME type or file-type label",
        examples=["image/dicom", "image/png"],
    )
    file_size: int = Field(
        ...,
        gt=0,
        description="File size in bytes",
        examples=[2_097_152],
    )


class JobResponse(BaseModel):
    """Full representation of a job returned by the API."""

    id: uuid.UUID = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status", examples=["pending"])
    original_filename: str = Field(..., description="Original file name")
    file_path: str = Field(..., description="Path to the file on disk")
    file_type: str = Field(..., description="File MIME type")
    file_size: int | None = Field(default=None, description="File size in bytes")
    created_at: datetime = Field(..., description="Timestamp when the job was created")
    updated_at: datetime = Field(..., description="Timestamp of the last status change")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Structured analysis result (available when completed)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error details (available when failed)",
    )

    model_config = {"from_attributes": True}


class JobStatus(BaseModel):
    """Lightweight status-only view of a job."""

    id: uuid.UUID = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")

    model_config = {"from_attributes": True}


class JobList(BaseModel):
    """Paginated list of jobs."""

    jobs: list[JobResponse] = Field(
        default_factory=list,
        description="Page of job records",
    )
    total: int = Field(..., ge=0, description="Total number of matching jobs")
    skip: int = Field(default=0, ge=0, description="Number of records skipped")
    limit: int = Field(default=20, ge=1, le=100, description="Max records returned")
