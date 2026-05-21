"""
Lumenis AI — Self-Critique Quality Assurance Service

Implements a "second-pass" audit of AI-generated imaging findings.
A separate Gemini call (low temperature, analytical mode) reviews
the primary findings against retrieved medical literature and flags
implausible, over-/under-called, or hallucinated results.

The audit output drives downstream filtering in the ReportGenerator:
  • KEEP   → finding passes QA unchanged
  • MODIFY → finding is retained but severity/confidence are revised
  • REMOVE → finding is dropped from the final report
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas.findings import Finding
from app.services.gemini_client import GeminiClient
from app.services.prompts import PromptTemplates

logger = logging.getLogger(__name__)


# ── Default audit result returned when Gemini call fails ──────────────
_EMPTY_AUDIT: dict[str, Any] = {
    "audited_findings": [],
    "missed_findings": [],
    "overall_quality_score": 0.5,
    "summary": "Audit could not be completed — defaulting to unaudited findings.",
}


class SelfCritiqueService:
    """Audits VLM findings against retrieved literature for clinical safety.

    Usage
    -----
    >>> svc = SelfCritiqueService()
    >>> audit = await svc.audit_findings(findings, retrieved_context_text)
    >>> print(audit["audited_findings"])
    """

    def __init__(self, gemini_client: GeminiClient | None = None) -> None:
        self._gemini = gemini_client or GeminiClient()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    async def audit_findings(
        self,
        findings: list[Finding],
        retrieved_context: str,
    ) -> dict[str, Any]:
        """Run the self-critique audit on a set of findings.

        Parameters
        ----------
        findings:
            The raw ``Finding`` objects produced by the VLM analysis step.
        retrieved_context:
            Pre-formatted text block of retrieved medical literature
            chunks (compiled from Qdrant retrieval).

        Returns
        -------
        dict
            Parsed audit result containing keys:
            ``audited_findings``, ``missed_findings``,
            ``overall_quality_score``, and ``summary``.
        """
        if not findings:
            logger.info("No findings to audit — returning empty audit.")
            return {
                "audited_findings": [],
                "missed_findings": [],
                "overall_quality_score": 1.0,
                "summary": "No findings were submitted for audit.",
            }

        # Serialise findings to JSON for the prompt
        findings_json = json.dumps(
            [f.model_dump() for f in findings],
            indent=2,
        )

        # Build the critique prompt
        prompt = PromptTemplates.build_critique_prompt(
            findings_json=findings_json,
            retrieved_context=retrieved_context,
        )

        try:
            logger.info(
                "Invoking Gemini self-critique for %d findings …",
                len(findings),
            )
            response_text = await self._gemini.generate_text(
                prompt=prompt,
                system_instruction=PromptTemplates.SELF_CRITIQUE_PROMPT,
                temperature=0.1,  # Low temp for analytical consistency
            )
            logger.debug(
                "Raw critique response (first 1000 chars): %s",
                response_text[:1000],
            )
            return self._parse_audit_response(response_text)

        except Exception as exc:
            logger.error(
                "Self-critique Gemini call failed: %s — returning default audit.",
                exc,
            )
            return dict(_EMPTY_AUDIT)

    # ──────────────────────────────────────────────────────────────────
    # Response parsing (mirrors GeminiClient / RAGPipeline strategies)
    # ──────────────────────────────────────────────────────────────────

    def _parse_audit_response(self, response_text: str) -> dict[str, Any]:
        """Parse the Gemini audit response into a structured dict."""
        text = response_text.strip()

        # Strategy 1: direct JSON parse
        parsed = self._try_parse_json(text)
        if parsed and self._is_valid_audit(parsed):
            return self._normalise_audit(parsed)

        # Strategy 2: extract from markdown code block
        parsed = self._extract_json_from_code_block(response_text)
        if parsed and self._is_valid_audit(parsed):
            return self._normalise_audit(parsed)

        # Strategy 3: regex brace matching
        parsed = self._extract_json_from_text(response_text)
        if parsed and self._is_valid_audit(parsed):
            return self._normalise_audit(parsed)

        logger.error(
            "All audit JSON parsing strategies failed. "
            "Response: %s",
            response_text[:1000],
        )
        return dict(_EMPTY_AUDIT)

    # ── Validation & normalisation ────────────────────────────────────

    @staticmethod
    def _is_valid_audit(data: dict) -> bool:
        """Check that the parsed dict has the expected audit keys."""
        return "audited_findings" in data

    @staticmethod
    def _normalise_audit(data: dict) -> dict[str, Any]:
        """Ensure all expected keys exist with sensible defaults."""
        audit: dict[str, Any] = {
            "audited_findings": data.get("audited_findings", []),
            "missed_findings": data.get("missed_findings", []),
            "overall_quality_score": float(
                data.get("overall_quality_score", 0.5)
            ),
            "summary": data.get("summary", "Audit completed."),
        }

        # Normalise verdicts to uppercase
        for af in audit["audited_findings"]:
            if "verdict" in af:
                af["verdict"] = str(af["verdict"]).upper().strip()
                if af["verdict"] not in ("KEEP", "MODIFY", "REMOVE"):
                    af["verdict"] = "KEEP"

            # Clamp revised confidence
            if af.get("revised_confidence") is not None:
                try:
                    af["revised_confidence"] = max(
                        0.0, min(1.0, float(af["revised_confidence"]))
                    )
                except (ValueError, TypeError):
                    af["revised_confidence"] = None

            # Normalise revised severity
            if af.get("revised_severity") is not None:
                sev = str(af["revised_severity"]).lower().strip()
                if sev not in ("low", "moderate", "high", "critical"):
                    af["revised_severity"] = None
                else:
                    af["revised_severity"] = sev

        # Normalise missed findings
        for mf in audit["missed_findings"]:
            if "severity" in mf:
                mf["severity"] = str(mf["severity"]).lower().strip()
            if "confidence" in mf:
                try:
                    mf["confidence"] = max(0.0, min(1.0, float(mf["confidence"])))
                except (ValueError, TypeError):
                    mf["confidence"] = 0.5

        return audit

    # ── JSON parsing helpers ──────────────────────────────────────────

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
