"""
Lumenis AI — RAG Orchestration Pipeline

Integrates findings from the VLM step with the Qdrant retrieval service
and Cross-Encoder re-ranker. Grounding is achieved via a single batched
Gemini call to ensure clinical safety, context integration, and 429 prevention.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas.findings import AnalysisResult, Finding
from app.schemas.report import Citation, ReportFinding
from app.services.gemini_client import GeminiClient
from app.services.prompts import PromptTemplates
from app.services.retriever import HybridRetriever, RetrievedDocument

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Orchestrates RAG retrieval, validation, and citation matching."""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self._retriever = retriever or HybridRetriever()
        self._gemini = gemini_client or GeminiClient()

    async def ground_findings(self, analysis_result: AnalysisResult) -> list[ReportFinding]:
        """Perform RAG grounding and citation enrichment for a list of findings.

        Parameters
        ----------
        analysis_result:
            The raw analysis results from the imaging step.

        Returns
        -------
        list[ReportFinding]
            A list of report findings enriched with explanations and literature citations.
        """
        findings = analysis_result.findings
        if not findings:
            logger.info("No findings to ground in RAG pipeline.")
            return []

        logger.info("Starting RAG grounding for %d findings ...", len(findings))

        # 1. Retrieve literature context for each finding
        finding_to_docs: dict[str, list[RetrievedDocument]] = {}
        all_unique_docs: dict[str, RetrievedDocument] = {}

        for finding in findings:
            # Query combines finding name and description for semantic search
            query = f"{finding.name} {finding.description}"
            logger.debug("Retrieving context for finding '%s' using query: %s", finding.name, query)
            
            docs = self._retriever.retrieve(query, top_k=3, prefetch_k=15)
            finding_to_docs[finding.name] = docs
            
            # Index documents globally for prompt construction
            for doc in docs:
                all_unique_docs[doc.source_id] = doc

        logger.info(
            "Retrieved %d unique literature chunks across all findings.",
            len(all_unique_docs),
        )

        # 2. Build RAG prompt using unique sources list
        sources_list = [
            {"id": doc_id, "text": doc.text}
            for doc_id, doc in all_unique_docs.items()
        ]
        
        findings_list = [f.model_dump() for f in findings]
        prompt = PromptTemplates.build_rag_grounding_prompt(findings_list, sources_list)

        # 3. Call Gemini to ground and synthesize explanations
        try:
            logger.info("Invoking Gemini for RAG synthesis ...")
            response_text = await self._gemini.generate_text(
                prompt=prompt,
                system_instruction=PromptTemplates.RAG_GROUNDING_SYSTEM_PROMPT,
                temperature=0.2,
            )
            logger.debug("Raw RAG response: %s", response_text[:1000])

            # Parse grounded findings list from Gemini response
            grounded_findings_map = self._parse_rag_response(response_text)
        except Exception as exc:
            logger.error("Gemini grounding call failed: %s. Falling back to default explanations.", exc)
            grounded_findings_map = {}

        # 4. Compile final list of ReportFinding objects with citation details
        report_findings: list[ReportFinding] = []

        for finding in findings:
            grounded_data = grounded_findings_map.get(finding.name)
            
            # Retrieve documents associated with *this* finding for local citation lookup
            local_docs = finding_to_docs.get(finding.name, [])
            local_doc_map = {doc.source_id: doc for doc in local_docs}

            # Calculate max relevance score of retrieved docs for confidence adjustment
            max_relevance = max([doc.relevance_score for doc in local_docs]) if local_docs else 0.0

            if grounded_data:
                explanation = grounded_data.get("explanation", finding.description)
                verified = grounded_data.get("verified", False)
                citation_ids = grounded_data.get("citation_source_ids", [])
                
                # Match citation IDs to actual documents
                citations: list[Citation] = []
                for cid in citation_ids:
                    # Check if document was retrieved
                    doc = local_doc_map.get(cid) or all_unique_docs.get(cid)
                    if doc:
                        citations.append(
                            Citation(
                                source_id=doc.source_id,
                                source_text=doc.text,
                                relevance_score=round(doc.relevance_score, 3),
                            )
                        )
                    else:
                        logger.warning("Gemini referenced source ID %s which is not in the retrieved documents.", cid)

                # Confidence adjustment:
                # If there are no citations, or the best retrieval score is extremely low (<0.4),
                # adjust finding confidence down by 20% to represent lack of grounding.
                adjusted_confidence = finding.confidence
                if not citations or max_relevance < 0.4:
                    adjusted_confidence = round(finding.confidence * 0.8, 3)
                    logger.info("Penalizing confidence of finding '%s' due to low literature grounding.", finding.name)

                # Create updated finding copy with adjusted confidence
                updated_finding = finding.model_copy(update={"confidence": adjusted_confidence})

                report_findings.append(
                    ReportFinding(
                        finding=updated_finding,
                        explanation=explanation,
                        citations=citations,
                        verified=verified and len(citations) > 0,
                    )
                )
            else:
                # Fallback: create default unverified report finding
                # Penalize confidence since it is ungrounded
                adjusted_confidence = round(finding.confidence * 0.7, 3)
                updated_finding = finding.model_copy(update={"confidence": adjusted_confidence})
                
                report_findings.append(
                    ReportFinding(
                        finding=updated_finding,
                        explanation=finding.description,
                        citations=[],
                        verified=False,
                    )
                )

        logger.info("Successfully grounded %d report findings.", len(report_findings))
        return report_findings

    def _parse_rag_response(self, response_text: str) -> dict[str, dict[str, Any]]:
        """Parse Gemini's RAG response text into a lookup map by finding name."""
        parsed = self._try_parse_json(response_text.strip())
        
        # Fallback to code block extract
        if parsed is None:
            parsed = self._extract_json_from_code_block(response_text)
            
        # Fallback to regex outermost extract
        if parsed is None:
            parsed = self._extract_json_from_text(response_text)

        if not parsed or "grounded_findings" not in parsed:
            logger.error("Failed to parse RAG grounding JSON structure.")
            return {}

        # Convert to lookup map
        findings_map: dict[str, dict[str, Any]] = {}
        for f in parsed["grounded_findings"]:
            name = f.get("finding_name")
            if name:
                findings_map[name] = f

        return findings_map

    # Helper parsing methods mirroring GeminiClient strategies for robustness
    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_json_from_code_block(text: str) -> dict | None:
        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    @staticmethod
    def _extract_json_from_text(text: str) -> dict | None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth != 0:
            return None
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return None
