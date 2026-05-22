"""
Lumenis AI — Gemini API Client

Production-grade client for Google Gemini 1.5 Pro multimodal medical
image analysis.  Handles structured JSON output, fallback parsing for
malformed responses, retry logic with exponential back-off, and
comprehensive error handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from PIL import Image
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.schemas.findings import AnalysisResult, Finding, ImageMetadata
from app.services.prompts import PromptTemplates

logger = logging.getLogger(__name__)

# ── Exceptions ────────────────────────────────────────────────────────

class GeminiClientError(Exception):
    """Base exception for all Gemini client errors."""


class GeminiAPIError(GeminiClientError):
    """Raised when the Gemini API returns an unrecoverable error."""


class GeminiParsingError(GeminiClientError):
    """Raised when the model response cannot be parsed into valid JSON."""


class GeminiQuotaExceededError(GeminiClientError):
    """Raised when the API quota or rate limit is hit."""


# ── Retry predicate ───────────────────────────────────────────────────

_RETRYABLE_EXCEPTIONS = (
    google_exceptions.ServiceUnavailable,
    google_exceptions.DeadlineExceeded,
    google_exceptions.InternalServerError,
    google_exceptions.ResourceExhausted,
    GeminiParsingError,
)


class GeminiClient:
    """Client for Google Gemini 1.5 Pro multimodal medical image analysis.

    Usage
    -----
    >>> client = GeminiClient()
    >>> result = await client.analyze_image("/path/to/xray.png")
    >>> print(result.findings)
    """

    MODEL_NAME: str = "gemini-3.1-pro-preview"

    # Safety settings — we need medical content to pass through
    _SAFETY_SETTINGS: list[dict[str, str]] = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # Generation config — low temperature for deterministic output
    _GENERATION_CONFIG = genai.types.GenerationConfig(
        temperature=0.2,
        top_p=0.8,
        top_k=40,
        max_output_tokens=4096,
    )

    def __init__(self, api_key: str | None = None) -> None:
        """Initialise the Gemini client.

        Parameters
        ----------
        api_key:
            Google Gemini API key.  Falls back to
            ``settings.GEMINI_API_KEY`` when *None*.

        Raises
        ------
        GeminiClientError
            If no API key is available.
        """
        self._api_key = api_key or settings.GEMINI_API_KEY
        if not self._api_key:
            raise GeminiClientError(
                "No Gemini API key provided. Set GEMINI_API_KEY in your "
                "environment or pass it explicitly to GeminiClient()."
            )
        genai.configure(api_key=self._api_key)
        logger.info("GeminiClient initialised with model %s", self.MODEL_NAME)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    async def analyze_image(
        self,
        image_input: str | Path | Image.Image,
        additional_context: dict[str, str] | None = None,
    ) -> AnalysisResult:
        """Send a medical image to Gemini and return structured findings.

        Parameters
        ----------
        image_input:
            File path (``str`` or ``Path``) to the image, or an
            in-memory ``PIL.Image.Image`` object.
        additional_context:
            Optional dict of clinical context to inject into the
            prompt (e.g. ``{"clinical_history": "..."}``).

        Returns
        -------
        AnalysisResult
            Validated Pydantic model containing findings and metadata.
        """
        image_path = self._resolve_image_path(image_input)
        return await self._analyze_with_retries(image_path, additional_context)

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        stream: bool = False,
    ) -> Any:
        """Send a text-only prompt to Gemini.

        If stream=True, returns the response object which can be iterated over to get chunks.
        """
        config = self._GENERATION_CONFIG
        if temperature != self._GENERATION_CONFIG.temperature:
            config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=4096,
            )

        model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            system_instruction=system_instruction,
            safety_settings=self._SAFETY_SETTINGS,
            generation_config=config,
        )

        if stream:
            def run_stream():
                return model.generate_content(prompt, stream=True)
            return await asyncio.to_thread(run_stream)

        def run_sync():
            return model.generate_content(prompt)
        
        response = await asyncio.to_thread(run_sync)
        return response.text

    # ──────────────────────────────────────────────────────────────────
    # Core analysis (with retry)
    # ──────────────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            "Gemini call failed (attempt %d): %s — retrying …",
            retry_state.attempt_number,
            retry_state.outcome.exception(),
        ),
    )
    async def _analyze_with_retries(
        self,
        image_path: Path,
        additional_context: dict[str, str] | None,
    ) -> AnalysisResult:
        """Execute the Gemini API call with automatic retries."""
        uploaded_file: Any | None = None
        try:
            # 1. Upload image to Gemini file service
            logger.info("Uploading image: %s", image_path.name)
            uploaded_file = genai.upload_file(
                path=str(image_path),
                display_name=image_path.name,
            )
            logger.info(
                "Image uploaded successfully — URI: %s",
                getattr(uploaded_file, "uri", "unknown"),
            )

            # 2. Create model instance with system instruction
            model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                system_instruction=PromptTemplates.ANALYSIS_SYSTEM_PROMPT,
                safety_settings=self._SAFETY_SETTINGS,
                generation_config=self._GENERATION_CONFIG,
            )

            # 3. Build user prompt
            user_prompt = PromptTemplates.build_analysis_prompt(
                metadata=additional_context,
            )

            # 4. Generate content (multimodal: image + text)
            logger.info("Sending analysis request to Gemini …")
            response = model.generate_content(
                [uploaded_file, user_prompt],
            )

            # 5. Extract text from response
            if not response.parts:
                # Check for blocked content
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    raise GeminiAPIError(
                        f"Prompt was blocked by Gemini safety filters: "
                        f"{response.prompt_feedback.block_reason}"
                    )
                raise GeminiAPIError(
                    "Gemini returned an empty response with no parts."
                )

            response_text = response.text
            logger.debug("Raw Gemini response (first 500 chars): %s", response_text[:500])

            # 6. Parse into AnalysisResult
            return self._parse_response(response_text)

        except (
            google_exceptions.InvalidArgument,
            google_exceptions.PermissionDenied,
            google_exceptions.NotFound,
        ) as exc:
            logger.error("Non-retryable Gemini API error: %s", exc)
            raise GeminiAPIError(f"Gemini API error: {exc}") from exc

        except google_exceptions.ResourceExhausted as exc:
            logger.warning("Gemini quota/rate limit exceeded: %s", exc)
            raise GeminiQuotaExceededError(
                "Gemini API quota or rate limit exceeded. "
                "Please try again later."
            ) from exc

        except GeminiClientError:
            raise  # Already wrapped — propagate as-is

        except Exception as exc:
            logger.exception("Unexpected error during Gemini analysis")
            raise GeminiAPIError(
                f"Unexpected error communicating with Gemini: {exc}"
            ) from exc

        finally:
            # Clean up uploaded file to avoid quota leaks
            if uploaded_file is not None:
                try:
                    genai.delete_file(uploaded_file.name)
                    logger.debug("Cleaned up uploaded file: %s", uploaded_file.name)
                except Exception:
                    logger.warning(
                        "Failed to delete uploaded file: %s",
                        getattr(uploaded_file, "name", "unknown"),
                        exc_info=True,
                    )

    # ──────────────────────────────────────────────────────────────────
    # Response Parsing
    # ──────────────────────────────────────────────────────────────────

    def _parse_response(self, response_text: str) -> AnalysisResult:
        """Parse Gemini's response text into a validated AnalysisResult.

        Attempts multiple extraction strategies in order:
        1. Direct JSON parse of the full response text.
        2. Extract JSON from markdown code fences.
        3. Regex-based extraction of the outermost JSON object.
        4. Return a fallback error result.

        Parameters
        ----------
        response_text:
            Raw text returned by Gemini.

        Returns
        -------
        AnalysisResult
        """
        # Strategy 1: direct parse
        parsed = self._try_parse_json(response_text.strip())
        if parsed is not None:
            return self._validate_parsed(parsed)

        # Strategy 2: extract from markdown code block
        parsed = self._extract_json_from_code_block(response_text)
        if parsed is not None:
            return self._validate_parsed(parsed)

        # Strategy 3: regex extraction
        parsed = self._extract_json_from_text(response_text)
        if parsed is not None:
            return self._validate_parsed(parsed)

        # Strategy 4: fallback
        logger.error(
            "All JSON parsing strategies failed.  Response text: %s",
            response_text[:1000],
        )
        return self._build_fallback_result(
            "Gemini returned a response that could not be parsed as "
            "valid JSON. The analysis could not be completed."
        )

    def _try_parse_json(self, text: str) -> dict | None:
        """Attempt ``json.loads`` on *text*; return *None* on failure."""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    def _extract_json_from_code_block(self, text: str) -> dict | None:
        """Extract JSON from a markdown `` ```json ... ``` `` block."""
        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return self._try_parse_json(match.group(1).strip())
        return None

    def _extract_json_from_text(self, text: str) -> dict | None:
        """Extract the outermost ``{…}`` JSON object via brace matching."""
        # Find the first '{' and greedily match to the last '}'
        start = text.find("{")
        if start == -1:
            return None

        # Walk through and track brace depth for robustness
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
        return self._try_parse_json(candidate)

    def _validate_parsed(self, data: dict) -> AnalysisResult:
        """Validate a parsed dict against the ``AnalysisResult`` schema.

        Applies light normalisation before validation:
        - Clamp confidence values.
        - Normalise severity strings to lower-case.
        - Filter out findings with confidence ≤ 0.3.
        """
        try:
            # Normalise findings
            raw_findings = data.get("findings", [])
            cleaned_findings: list[dict] = []
            for f in raw_findings:
                # Normalise severity
                if "severity" in f:
                    f["severity"] = str(f["severity"]).lower().strip()
                    if f["severity"] not in ("low", "moderate", "high", "critical"):
                        f["severity"] = "moderate"  # safe default

                # Clamp confidence
                if "confidence" in f:
                    try:
                        f["confidence"] = max(0.0, min(1.0, float(f["confidence"])))
                    except (ValueError, TypeError):
                        f["confidence"] = 0.5

                # Filter sub-threshold findings
                if f.get("confidence", 0) > 0.3:
                    cleaned_findings.append(f)

            data["findings"] = cleaned_findings

            # Normalise metadata
            meta = data.get("metadata", {})
            if "quality_score" in meta:
                try:
                    meta["quality_score"] = max(0.0, min(1.0, float(meta["quality_score"])))
                except (ValueError, TypeError):
                    meta["quality_score"] = 0.5

            return AnalysisResult.model_validate(data)

        except Exception as exc:
            logger.warning(
                "Pydantic validation failed after normalisation: %s", exc
            )
            return self._build_fallback_result(
                f"Response JSON did not conform to the expected schema: {exc}"
            )

    # ──────────────────────────────────────────────────────────────────
    # Fallback Result
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_fallback_result(error_msg: str) -> AnalysisResult:
        """Return a minimal valid AnalysisResult when parsing fails.

        The error message is stored in the ``body_part`` field so that
        downstream consumers can detect the failure.

        Parameters
        ----------
        error_msg:
            Human-readable description of what went wrong.
        """
        logger.warning("Returning fallback AnalysisResult: %s", error_msg)
        return AnalysisResult(
            findings=[],
            metadata=ImageMetadata(
                modality="Unknown",
                body_part=f"PARSE_ERROR: {error_msg[:200]}",
                quality_score=0.0,
            ),
        )

    # ──────────────────────────────────────────────────────────────────
    # Image resolution helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_image_path(image_input: str | Path | Image.Image) -> Path:
        """Convert various image input types to a ``Path``.

        If *image_input* is a PIL Image, it is saved to a temporary
        file so it can be uploaded to the Gemini file service.
        """
        if isinstance(image_input, Image.Image):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False,
            )
            image_input.save(tmp, format="PNG")
            tmp.close()
            logger.debug("Saved PIL Image to temp file: %s", tmp.name)
            return Path(tmp.name)

        path = Path(image_input)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Image path is not a regular file: {path}")
        return path
