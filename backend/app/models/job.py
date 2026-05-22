"""
Lumenis AI — Job Model

Represents an image-analysis job submitted by a user.
Tracks status, uploaded file metadata, and analysis results.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatus(str, enum.Enum):
    """Lifecycle states of an analysis job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """
    Persistent record for a single image-analysis request.

    Attributes
    ----------
    id : UUID
        Unique job identifier (auto-generated).
    status : JobStatus
        Current processing state.
    file_name : str
        Original name of the uploaded file.
    file_type : str
        MIME type or extension category (e.g. ``image/dicom``).
    file_size : int
        Size of the uploaded file in bytes.
    result : dict | None
        JSON blob containing the full ``AnalysisResult`` once processing
        completes.  ``None`` while the job is still in progress.
    error_message : str | None
        Human-readable error description when ``status == FAILED``.
    report : Report
        One-to-one relationship to the generated clinical report.
    """

    __tablename__ = "jobs"

    status: Mapped[JobStatus] = mapped_column(
        String(50),
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Original file name as uploaded by the user",
    )

    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Absolute path to the file on disk",
    )

    file_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        doc="File size in bytes",
    )

    result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        doc="Structured analysis result (JSON)",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    # ── Relationships ──────────────────────────────────────────────
    report: Mapped["Report"] = relationship(
        "Report",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Job id={self.id!s} status={self.status.value!r} "
            f"file={self.original_filename!r}>"
        )
