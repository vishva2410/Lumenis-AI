from __future__ import annotations
import uuid
from sqlalchemy import String, Date, func, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Patient(Base):
    """
    Persistent record for a patient.
    """
    __tablename__ = "patients"

    patient_mrn: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False, doc="Medical Record Number")
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    date_of_birth: Mapped[Date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(32), nullable=False)

    studies: Mapped[list["Study"]] = relationship(
        "Study",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Patient {self.first_name} {self.last_name} ({self.patient_mrn})>"
