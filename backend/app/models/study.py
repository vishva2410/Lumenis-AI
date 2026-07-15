from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Study(Base):
    """
    Persistent record for an imaging study session belonging to a Patient.
    """
    __tablename__ = "studies"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    study_description: Mapped[str] = mapped_column(String(256), nullable=False)
    modality: Mapped[str] = mapped_column(String(64), nullable=False)
    study_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    patient: Mapped["Patient"] = relationship("Patient", back_populates="studies")
    
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="study",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Study {self.study_description} ({self.modality})>"
