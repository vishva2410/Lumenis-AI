"""
Lumenis AI — Analysis Celery Task (Phase 4 — Full Pipeline)

Orchestrates the complete medical image analysis pipeline:

  1. Image pre-processing (DICOM / JPEG / PNG / PDF)
  2. Gemini 1.5 Pro multimodal analysis → structured findings
  3. RAG context retrieval & grounding from Qdrant
  4. Self-critique quality assurance audit
  5. Final report generation with citations & recommendations
  6. Database persistence

The task runs in a synchronous Celery worker context.  Async
operations (Gemini calls, RAG pipeline) are bridged via
``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime, timezone

import redis

from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_sync_db_session():
    """
    Create a synchronous SQLAlchemy session for use inside Celery workers.

    Celery tasks run in a synchronous context, so we cannot use the
    async ``get_db`` dependency from FastAPI. Instead we use the
    synchronous ``SessionLocal`` factory.
    """
    from app.db.session import SessionLocal

    return SessionLocal()


def _publish_status(job_id: str, step_index: int, message: str) -> None:
    """Publish a status update to Redis for the SSE endpoint."""
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.publish(f"job:{job_id}:status", json.dumps({"step": step_index, "message": message}))
    except Exception as exc:
        logger.warning("Failed to publish status to Redis: %s", exc)


@celery_app.task(
    bind=True,
    name="app.workers.analysis_task.run_analysis",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_analysis(self, job_id: str, file_path: str) -> dict:
    """
    Run the full medical image analysis pipeline for a given job.

    Args:
        job_id:    UUID string of the Job record.
        file_path: Absolute path to the uploaded file on disk.

    Returns:
        A dict summarising the outcome (serialised as the Celery result).

    Pipeline steps:
        1. Image pre-processing & normalisation
        2. Gemini multimodal analysis → structured findings JSON
        3. RAG grounding — retrieve literature & validate findings
        4. Self-critique audit
        5. Report generation with citations & recommendations
    """
    from app.models.job import Job
    from app.models.report import Report

    db = _get_sync_db_session()
    logger.info("Starting analysis for job %s (file: %s)", job_id, file_path)

    job = None
    try:
        # ── Fetch the job ────────────────────────────────────────────
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if job is None:
            logger.error("Job %s not found in database — aborting.", job_id)
            return {"status": "error", "detail": "Job not found"}

        # ── Mark as processing ───────────────────────────────────────
        job.status = "processing"
        db.commit()
        logger.info("Job %s status → processing", job_id)

        # ─────────────────────────────────────────────────────────────
        # STEP 1: Image Pre-processing
        # ─────────────────────────────────────────────────────────────
        _publish_status(job_id, 1, "Image pre-processing started...")
        logger.info("Step 1: Image pre-processing …")

        # Check if this is a PDF (text-based analysis) or an image
        is_pdf = file_path.lower().endswith(".pdf")

        additional_context = None

        if is_pdf:
            # Parse PDF and send extracted text to Gemini
            from app.services.pdf_parser import PDFParser

            parser = PDFParser()
            parsed_report = parser.parse(file_path)
            logger.info(
                "PDF parsed: %d pages, sections=%s, scanned=%s",
                parsed_report.page_count,
                list(parsed_report.sections.keys()),
                parsed_report.is_scanned,
            )

            if parsed_report.is_scanned:
                logger.warning(
                    "PDF appears to be scanned — text extraction may be incomplete."
                )

            # Use the parsed text as additional context for Gemini
            additional_context = {
                "document_type": "PDF Radiology Report",
                "extracted_text": parsed_report.full_text[:8000],  # limit context length
            }
            if parsed_report.sections.get("findings"):
                additional_context["findings_section"] = parsed_report.sections["findings"]
            if parsed_report.sections.get("impression"):
                additional_context["impression_section"] = parsed_report.sections["impression"]
            if parsed_report.sections.get("clinical_history"):
                additional_context["clinical_history"] = parsed_report.sections["clinical_history"]

            processed_image_path = None

        else:
            # Image file — run through the image processor
            from app.services.image_processor import ImageProcessor

            processor = ImageProcessor(target_size=1024)
            processed = processor.process(file_path)

            logger.info(
                "Image processed: format=%s, path=%s, metadata_keys=%s",
                processed.original_format,
                processed.image_path,
                list(processed.metadata.keys()),
            )

            processed_image_path = processed.image_path

            # Pass extracted DICOM metadata as additional context
            if processed.original_format == "dicom":
                dicom_meta = {}
                if processed.metadata.get("modality"):
                    dicom_meta["modality"] = processed.metadata["modality"]
                if processed.metadata.get("study_description"):
                    dicom_meta["study_description"] = processed.metadata["study_description"]
                if processed.metadata.get("series_description"):
                    dicom_meta["series_description"] = processed.metadata["series_description"]
                if dicom_meta:
                    additional_context = dicom_meta

        # ─────────────────────────────────────────────────────────────
        # STEP 2: Gemini Multimodal Analysis
        # ─────────────────────────────────────────────────────────────
        _publish_status(job_id, 2, "Multimodal VLM analysis in progress...")
        logger.info("Step 2: Gemini multimodal analysis …")

        from app.services.gemini_client import GeminiClient

        client = GeminiClient()

        if is_pdf and processed_image_path is None:
            logger.info("PDF text-only analysis — no image to upload to Gemini.")

            from app.schemas.findings import AnalysisResult, ImageMetadata

            analysis_result = AnalysisResult(
                findings=[],
                metadata=ImageMetadata(
                    modality="PDF Report",
                    body_part="See report text",
                    quality_score=0.8,
                ),
            )
        else:
            # Standard image analysis
            image_to_analyze = processed_image_path or file_path
            analysis_result = asyncio.run(
                client.analyze_image(
                    image_input=image_to_analyze,
                    additional_context=additional_context,
                )
            )

        logger.info(
            "Gemini analysis complete: %d findings detected",
            len(analysis_result.findings),
        )

        # Log each finding at info level
        for i, finding in enumerate(analysis_result.findings):
            logger.info(
                "  Finding %d: %s | severity=%s | confidence=%.2f | region=%s",
                i + 1,
                finding.name,
                finding.severity,
                finding.confidence,
                finding.region,
            )

        # ─────────────────────────────────────────────────────────────
        # STEP 3: RAG Grounding — retrieve literature & validate
        # ─────────────────────────────────────────────────────────────
        _publish_status(job_id, 3, "RAG Grounding: Retrieving clinical literature...")
        logger.info("Step 3: RAG grounding …")

        grounded_findings = []
        retrieved_context_text = ""

        if analysis_result.findings:
            try:
                from app.services.rag_pipeline import RAGPipeline

                rag = RAGPipeline(gemini_client=client)
                grounded_findings = asyncio.run(
                    rag.ground_findings(analysis_result)
                )

                # Compile retrieved context for self-critique
                # Extract unique texts from all citations
                seen_texts: set[str] = set()
                context_parts: list[str] = []
                for rf in grounded_findings:
                    for citation in rf.citations:
                        if citation.source_text not in seen_texts:
                            seen_texts.add(citation.source_text)
                            context_parts.append(
                                f"[{citation.source_id}]: {citation.source_text}"
                            )
                retrieved_context_text = "\n\n".join(context_parts)

                logger.info(
                    "RAG grounding complete: %d grounded findings, "
                    "%d unique literature sources.",
                    len(grounded_findings),
                    len(seen_texts),
                )

            except Exception as exc:
                logger.error(
                    "RAG grounding failed: %s — proceeding with "
                    "ungrounded findings.",
                    exc,
                )
                # Fallback: wrap raw findings as ungrounded ReportFindings
                from app.schemas.report import ReportFinding

                grounded_findings = [
                    ReportFinding(
                        finding=f,
                        explanation=f.description,
                        citations=[],
                        verified=False,
                    )
                    for f in analysis_result.findings
                ]
        else:
            logger.info("No findings to ground — skipping RAG pipeline.")

        # ─────────────────────────────────────────────────────────────
        # STEP 4: Self-Critique Audit
        # ─────────────────────────────────────────────────────────────
        _publish_status(job_id, 4, "Running self-critique QA audit...")
        logger.info("Step 4: Self-critique audit …")

        audit_results = None

        if analysis_result.findings:
            try:
                from app.services.self_critique import SelfCritiqueService

                critique_svc = SelfCritiqueService(gemini_client=client)
                audit_results = asyncio.run(
                    critique_svc.audit_findings(
                        findings=analysis_result.findings,
                        retrieved_context=retrieved_context_text,
                    )
                )
                logger.info(
                    "Self-critique complete: quality_score=%.2f, "
                    "%d audited, %d missed.",
                    audit_results.get("overall_quality_score", 0.0),
                    len(audit_results.get("audited_findings", [])),
                    len(audit_results.get("missed_findings", [])),
                )

            except Exception as exc:
                logger.error(
                    "Self-critique failed: %s — proceeding without audit.",
                    exc,
                )
        else:
            logger.info("No findings to audit — skipping self-critique.")

        # ─────────────────────────────────────────────────────────────
        # STEP 5: Report Generation
        # ─────────────────────────────────────────────────────────────
        _publish_status(job_id, 5, "Synthesizing final clinical report...")
        logger.info("Step 5: Report generation …")

        from app.services.report_generator import ReportGenerator

        report_gen = ReportGenerator(gemini_client=client)
        full_report = asyncio.run(
            report_gen.generate_report(
                job_id=job.id,
                grounded_findings=grounded_findings,
                metadata=analysis_result.metadata,
                audit_results=audit_results,
            )
        )

        logger.info(
            "Report generated: severity=%s, confidence=%.3f, "
            "%d findings, %d recommendations.",
            full_report.severity_overall,
            full_report.confidence_score,
            len(full_report.findings),
            len(full_report.recommendations),
        )

        # ── Build result JSON ────────────────────────────────────────
        result_data = analysis_result.model_dump()
        result_data["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        result_data["file_path"] = file_path
        result_data["report_summary"] = full_report.summary
        result_data["severity_overall"] = full_report.severity_overall
        result_data["recommendations"] = full_report.recommendations

        if audit_results:
            result_data["audit_quality_score"] = audit_results.get(
                "overall_quality_score", None
            )
            result_data["audit_summary"] = audit_results.get("summary", None)

        # ── Persist report to database ───────────────────────────────
        # Serialise report findings for DB storage
        findings_for_db = [
            {
                "finding": rf.finding.model_dump(),
                "explanation": rf.explanation,
                "citations": [c.model_dump() for c in rf.citations],
                "verified": rf.verified,
            }
            for rf in full_report.findings
        ]

        citations_for_db = []
        for rf in full_report.findings:
            for c in rf.citations:
                citations_for_db.append(c.model_dump())

        report_record = Report(
            job_id=job.id,
            summary=full_report.summary,
            findings=findings_for_db,
            severity_overall=full_report.severity_overall,
            confidence_score=full_report.confidence_score,
            citations=citations_for_db,
        )
        db.add(report_record)

        # ── Mark as completed ────────────────────────────────────────
        job.status = "completed"
        job.result = result_data
        db.commit()
        
        _publish_status(job_id, 6, "Analysis completed successfully.")
        
        logger.info(
            "Job %s status → completed (%d findings)",
            job_id,
            len(full_report.findings),
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "findings_count": len(full_report.findings),
            "severity": full_report.severity_overall,
            "confidence": full_report.confidence_score,
        }

    except Exception as exc:
        # ── Handle failure ───────────────────────────────────────────
        logger.error(
            "Analysis failed for job %s: %s\n%s",
            job_id,
            exc,
            traceback.format_exc(),
        )

        try:
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:2048]
                db.commit()
                _publish_status(job_id, -1, f"Analysis failed: {str(exc)[:100]}")
        except Exception as db_exc:
            logger.error("Failed to update job status after error: %s", db_exc)
            db.rollback()

        # Let Celery retry if retries remain
        raise self.retry(exc=exc)

    finally:
        db.close()
