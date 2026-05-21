"""
Lumenis AI — Finding & Image-Metadata Schemas

Pydantic models for individual analysis findings and
the structured result returned by the imaging pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImageMetadata(BaseModel):
    """Technical metadata extracted from the medical image."""

    modality: str = Field(
        ...,
        description="Imaging modality (e.g. CT, MRI, X-Ray, Ultrasound)",
        examples=["CT", "MRI", "X-Ray"],
    )
    body_part: str = Field(
        ...,
        description="Anatomical region depicted in the image",
        examples=["Chest", "Brain", "Abdomen"],
    )
    quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Image quality score (0 = unusable, 1 = optimal)",
    )


class Finding(BaseModel):
    """A single clinical finding detected during analysis."""

    name: str = Field(
        ...,
        description="Short label for the finding",
        examples=["Pulmonary Nodule", "Pleural Effusion"],
    )
    severity: str = Field(
        ...,
        description="Severity level (e.g. low, moderate, high, critical)",
        examples=["low", "moderate", "high", "critical"],
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in this finding (0–1)",
    )
    region: str = Field(
        ...,
        description="Anatomical region or bounding-box descriptor",
        examples=["Right upper lobe", "Left hemisphere"],
    )
    description: str = Field(
        ...,
        description="Detailed narrative description of the finding",
    )


class AnalysisResult(BaseModel):
    """Complete output of the image-analysis pipeline."""

    findings: list[Finding] = Field(
        default_factory=list,
        description="Ordered list of detected findings",
    )
    metadata: ImageMetadata = Field(
        ...,
        description="Technical metadata about the analysed image",
    )
