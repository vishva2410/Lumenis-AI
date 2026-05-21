"""
Lumenis AI — Report Generator

Combines RAG-grounded findings, self-critique audit results, and
metadata into a final ``FullReport`` Pydantic model ready for
database persistence and API delivery.

Pipeline position:
  VLM Findings → RAG Grounding → Self-Critique Audit → **Report Generator** → DB
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app.schemas.findings import Finding, ImageMetadata
from app.schemas.report import Citation, FullReport, ReportFinding
from app.services.gemini_client import GeminiClient
from app.services.prompts import PromptTemplates

logger = logging.getLogger(__name__)

# ── Severity ordering for comparisons ────────────────────────────────
_SEVERITY_RANK: dict[str, int] = {
    "low": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}

# ── Recommendation templates keyed by severity ──────────────────────
_SEVERITY_RECOMMENDATIONS: dict[str, list[str]] = {
    "critical": [
        "Immediate clinical correlation and urgent specialist consultation recommended.",
        "Consider emergent follow-up imaging if clinically indicated.",
        "Ensure findings are communicated to the referring physician within the hour.",
    ],
    "high": [
        "Prompt specialist referral recommended within 24-48 hours.",
        "Consider dedicated follow-up imaging (CT/MRI) for further characterisation.",
        "Clinical correlation with patient history and laboratory findings is essential.",
    ],
    "moderate": [
        "Routine follow-up imaging recommended per applicable guidelines.",
        "Clinical correlation advised; consider repeat imaging in 3-6 months.",
        "Discuss findings with the patient and primary care provider.",
    ],
    "low": [
        "No urgent action required; findings are likely incidental.",
        "Routine surveillance as per standard clinical protocols.",
    ],
}

# ── Report summary synthesis prompt ──────────────────────────────────
_SUMMARY_SYSTEM_PROMPT = (
    "You are a senior radiologist writing a concise, professional narrative "
    "summary for a clinical imaging report. The summary should be 3-5 sentences, "
    "written in plain English suitable for both clinicians and patients. "
    "Mention the imaging modality, body part, key findings, overall severity, "
    "and recommended next steps. Do NOT use markdown or bullet points. "
    "Return ONLY the summary text — no JSON, no code fences."
)


class ReportGenerator:
    """Constructs the final clinical report from grounded, audited findings.

    Usage
    -----
    >>> gen = ReportGenerator()
    >>> report = await gen.generate_report(
    ...     job_id=uuid.UUID("..."),
    ...     grounded_findings=grounded,
    ...     metadata=analysis_result.metadata,
    ...     audit_results=audit,
    ... )
    """

    def __init__(self, gemini_client: GeminiClient | None = None) -> None:
        self._gemini = gemini_client or GeminiClient()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    async def generate_report(
        self,
        job_id: uuid.UUID,
        grounded_findings: list[ReportFinding],
        metadata: ImageMetadata,
        audit_results: dict[str, Any] | None = None,
    ) -> FullReport:
        """Build the final ``FullReport``.

        Parameters
        ----------
        job_id:
            UUID of the originating analysis job.
        grounded_findings:
            Findings already enriched with explanations and citations
            by the RAG pipeline.
        metadata:
            Image metadata (modality, body_part, quality_score).
        audit_results:
            Optional self-critique audit dict.  When provided, findings
            are filtered/adjusted according to audit verdicts.

        Returns
        -------
        FullReport
            A fully populated Pydantic report model.
        """
        logger.info(
            "Generating report for job %s (%d grounded findings) …",
            job_id,
            len(grounded_findings),
        )

        # 1. Apply audit adjustments
        refined_findings = self._apply_audit(grounded_findings, audit_results)

        # 2. Add any missed findings flagged by the audit
        missed = self._build_missed_findings(audit_results)
        if missed:
            logger.info("Adding %d missed findings from audit.", len(missed))
            refined_findings.extend(missed)

        # 3. Sort by severity (critical first), then confidence descending
        refined_findings.sort(
            key=lambda rf: (
                -_SEVERITY_RANK.get(rf.finding.severity, 0),
                -rf.finding.confidence,
            ),
        )

        # 4. Compute aggregate statistics
        overall_severity = self._compute_overall_severity(refined_findings)
        avg_confidence = self._compute_avg_confidence(refined_findings)

        # 5. Build recommendations
        recommendations = self._build_recommendations(
            refined_findings, overall_severity
        )

        # 6. Generate narrative summary via Gemini
        summary = await self._generate_summary(
            refined_findings, metadata, overall_severity
        )

        # 7. Assemble the FullReport
        report = FullReport(
            job_id=job_id,
            summary=summary,
            findings=refined_findings,
            severity_overall=overall_severity,
            confidence_score=round(avg_confidence, 3),
            recommendations=recommendations,
        )

        logger.info(
            "Report generated: severity=%s, confidence=%.3f, %d findings, %d recommendations.",
            overall_severity,
            avg_confidence,
            len(refined_findings),
            len(recommendations),
        )
        return report

    # ──────────────────────────────────────────────────────────────────
    # Audit application
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_audit(
        findings: list[ReportFinding],
        audit: dict[str, Any] | None,
    ) -> list[ReportFinding]:
        """Filter and adjust findings based on audit verdicts."""
        if not audit or not audit.get("audited_findings"):
            return list(findings)  # shallow copy

        # Build lookup: original_name → audit entry
        audit_map: dict[str, dict] = {}
        for af in audit["audited_findings"]:
            name = af.get("original_name", "").strip()
            if name:
                audit_map[name] = af

        refined: list[ReportFinding] = []

        for rf in findings:
            entry = audit_map.get(rf.finding.name)
            if not entry:
                # No audit opinion → keep unchanged
                refined.append(rf)
                continue

            verdict = entry.get("verdict", "KEEP").upper()

            if verdict == "REMOVE":
                logger.info(
                    "Audit REMOVED finding '%s': %s",
                    rf.finding.name,
                    entry.get("reasoning", "no reason"),
                )
                continue

            if verdict == "MODIFY":
                updates: dict[str, Any] = {}
                if entry.get("revised_severity"):
                    updates["severity"] = entry["revised_severity"]
                if entry.get("revised_confidence") is not None:
                    updates["confidence"] = entry["revised_confidence"]
                if updates:
                    updated_finding = rf.finding.model_copy(update=updates)
                    rf = ReportFinding(
                        finding=updated_finding,
                        explanation=rf.explanation,
                        citations=rf.citations,
                        verified=rf.verified,
                    )
                    logger.info(
                        "Audit MODIFIED finding '%s': %s → %s",
                        rf.finding.name,
                        entry.get("reasoning", ""),
                        updates,
                    )

            refined.append(rf)

        return refined

    @staticmethod
    def _build_missed_findings(
        audit: dict[str, Any] | None,
    ) -> list[ReportFinding]:
        """Convert missed findings from the audit into ReportFinding objects."""
        if not audit or not audit.get("missed_findings"):
            return []

        missed_rfs: list[ReportFinding] = []
        for mf in audit["missed_findings"]:
            try:
                finding = Finding(
                    name=mf.get("name", "Unknown Finding"),
                    severity=mf.get("severity", "moderate"),
                    confidence=max(0.31, min(1.0, float(mf.get("confidence", 0.5)))),
                    region=mf.get("region", "Unspecified"),
                    description=mf.get("description", "Identified during quality audit."),
                )
                missed_rfs.append(
                    ReportFinding(
                        finding=finding,
                        explanation=(
                            f"This finding was identified during the quality "
                            f"assurance review: {finding.description}"
                        ),
                        citations=[],
                        verified=False,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Could not construct missed finding from audit: %s — %s",
                    mf,
                    exc,
                )
        return missed_rfs

    # ──────────────────────────────────────────────────────────────────
    # Aggregate computations
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_overall_severity(findings: list[ReportFinding]) -> str:
        if not findings:
            return "low"
        return max(
            (rf.finding.severity for rf in findings),
            key=lambda s: _SEVERITY_RANK.get(s, 0),
        )

    @staticmethod
    def _compute_avg_confidence(findings: list[ReportFinding]) -> float:
        if not findings:
            return 0.0
        return sum(rf.finding.confidence for rf in findings) / len(findings)

    # ──────────────────────────────────────────────────────────────────
    # Recommendations
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_recommendations(
        findings: list[ReportFinding],
        overall_severity: str,
    ) -> list[str]:
        """Build actionable clinical recommendations."""
        recs: list[str] = []

        # Global recommendations based on overall severity
        severity_recs = _SEVERITY_RECOMMENDATIONS.get(overall_severity, [])
        recs.extend(severity_recs)

        # Finding-specific recommendations
        for rf in findings:
            name = rf.finding.name
            sev = rf.finding.severity

            if sev == "critical":
                recs.append(
                    f"CRITICAL — {name}: Immediate specialist evaluation required."
                )
            elif sev == "high":
                recs.append(
                    f"{name}: Recommend dedicated follow-up study within 2 weeks."
                )

            # Pulmonary nodule → Fleischner Society guidelines
            if "nodule" in name.lower() and "pulmonary" in name.lower():
                recs.append(
                    f"{name}: Follow Fleischner Society guidelines for "
                    f"incidental pulmonary nodule management. "
                    f"Nodule size and patient risk factors determine follow-up interval."
                )

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return unique_recs

    # ──────────────────────────────────────────────────────────────────
    # Narrative summary via Gemini
    # ──────────────────────────────────────────────────────────────────

    async def _generate_summary(
        self,
        findings: list[ReportFinding],
        metadata: ImageMetadata,
        overall_severity: str,
    ) -> str:
        """Generate a plain-English narrative summary using Gemini."""
        if not findings:
            return (
                f"Analysis of {metadata.modality} image "
                f"({metadata.body_part}): No significant findings detected. "
                f"Image quality score: {metadata.quality_score:.1f}/1.0."
            )

        findings_summary = "\n".join(
            f"- {rf.finding.name} (severity: {rf.finding.severity}, "
            f"confidence: {rf.finding.confidence:.0%}, "
            f"region: {rf.finding.region}): {rf.finding.description}"
            for rf in findings
        )

        prompt = (
            f"Imaging Modality: {metadata.modality}\n"
            f"Body Part: {metadata.body_part}\n"
            f"Image Quality: {metadata.quality_score:.1f}/1.0\n"
            f"Overall Severity: {overall_severity}\n"
            f"Number of Findings: {len(findings)}\n\n"
            f"Findings:\n{findings_summary}\n\n"
            f"Write the narrative summary now."
        )

        try:
            summary = await self._gemini.generate_text(
                prompt=prompt,
                system_instruction=_SUMMARY_SYSTEM_PROMPT,
                temperature=0.3,
            )
            # Strip any accidental code fences or extra whitespace
            summary = summary.strip().strip("`").strip()
            if summary:
                return summary
        except Exception as exc:
            logger.warning(
                "Gemini summary generation failed: %s — using fallback.",
                exc,
            )

        # Fallback: deterministic summary
        finding_names = [rf.finding.name for rf in findings]
        return (
            f"Analysis of {metadata.modality} image "
            f"({metadata.body_part}): "
            f"{len(findings)} finding(s) detected — "
            f"{', '.join(finding_names)}. "
            f"Overall severity: {overall_severity}."
        )
