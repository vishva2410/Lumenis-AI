"""
Lumenis AI — Report Model

Stores the generated clinical report for a completed analysis job.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job


class Report(Base):
    """
    Clinical report generated after image analysis.

    Attributes
    ----------
    id : UUID
        Unique report identifier.
    job_id : UUID
        Foreign key linking back to the originating ``Job``.
    findings : list[dict]
        JSON array of structured finding objects.
    summary : str
        Free-text narrative summary of all findings.
    severity_overall : str
        Aggregate severity label for the entire report
        (e.g. ``"low"``, ``"moderate"``, ``"high"``, ``"critical"``).
    confidence_score : float
        Weighted average confidence across all findings (0–1).
    citations : list[dict]
        JSON array of citation objects referencing medical literature.
    job : Job
        Back-reference to the parent job.
    """

    __tablename__ = "reports"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    findings: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="Array of structured finding objects",
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    severity_overall: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="low",
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        doc="Aggregated confidence (0–1)",
    )

    citations: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="Array of citation objects",
    )

    # ── Relationships ──────────────────────────────────────────────
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="report",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Report id={self.id!s} job_id={self.job_id!s} "
            f"severity={self.severity_overall!r}>"
        )
