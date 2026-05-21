"""
Medical PDF Report Parser
=========================

Extracts and structures text from medical / radiology PDF reports using
PyMuPDF (fitz).  Identifies common report sections (demographics, findings,
impression, etc.), detects scanned documents, and returns a structured
``ParsedReport`` model.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

import fitz  # PyMuPDF

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section heading patterns
# ---------------------------------------------------------------------------
# Each key is a canonical section name; values are regex patterns (case-
# insensitive) that match common heading variants in radiology / oncology
# reports.

_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "patient_demographics": re.compile(
        r"^[\s#*]*(?:patient\s+(?:information|demographics|data|details)"
        r"|demographics|patient\s+name)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "clinical_history": re.compile(
        r"^[\s#*]*(?:clinical\s+(?:history|information|indication)"
        r"|history|indication|reason\s+for\s+(?:exam|study|examination)"
        r"|clinical\s+data|relevant\s+history)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "technique": re.compile(
        r"^[\s#*]*(?:technique|protocol|procedure|exam\s+type"
        r"|examination\s+technique|imaging\s+protocol)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "comparison": re.compile(
        r"^[\s#*]*(?:comparison|prior\s+(?:studies|exams|examinations)"
        r"|previous\s+(?:studies|imaging))"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "findings": re.compile(
        r"^[\s#*]*(?:findings|results|observations|description"
        r"|imaging\s+findings|radiologic\s+findings|body)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "impression": re.compile(
        r"^[\s#*]*(?:impression|conclusion|summary|interpretation"
        r"|overall\s+impression|diagnostic\s+impression|assessment)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "recommendations": re.compile(
        r"^[\s#*]*(?:recommendation[s]?|follow[\s-]*up|suggested\s+(?:follow[\s-]*up|action)"
        r"|plan|next\s+steps|additional\s+recommendations)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "addendum": re.compile(
        r"^[\s#*]*(?:addendum|amendment|correction|supplemental)"
        r"[\s:]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# Threshold: if extracted text per page averages below this many chars,
# we treat the PDF as a scanned document.
_SCANNED_CHAR_THRESHOLD = 50


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ParsedReport(BaseModel):
    """Structured output from parsing a medical PDF report."""

    full_text: str = Field(
        ...,
        description="Complete extracted text from the PDF.",
    )
    sections: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Identified report sections mapped by canonical name "
            "(e.g. 'findings', 'impression')."
        ),
    )
    page_count: int = Field(
        ...,
        description="Number of pages in the PDF.",
    )
    has_images: bool = Field(
        default=False,
        description="Whether the PDF contains embedded raster images.",
    )
    is_scanned: bool = Field(
        default=False,
        description=(
            "True when the PDF appears to be a scanned document "
            "(very little extractable text relative to page count)."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="PDF-level metadata (author, creation date, etc.).",
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class PDFParser:
    """Extract and structure text from medical PDF reports.

    Usage
    -----
    >>> parser = PDFParser()
    >>> report = parser.parse("/path/to/report.pdf")
    >>> print(report.sections.get("findings", "No findings section found."))
    """

    def parse(self, file_path: str) -> ParsedReport:
        """Parse a PDF file and return a structured ``ParsedReport``.

        Parameters
        ----------
        file_path : str
            Path to the PDF file.

        Returns
        -------
        ParsedReport
            Structured report with extracted text, identified sections,
            and document metadata.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        ValueError
            If the file is not a valid PDF or cannot be opened.
        """
        logger.info("Parsing PDF: %s", file_path)

        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ValueError(
                f"Unable to open PDF file: {file_path}. Error: {exc}"
            ) from exc

        try:
            page_count = len(doc)
            if page_count == 0:
                raise ValueError(f"PDF has no pages: {file_path}")

            # --- Extract text ---
            raw_text = self._extract_text(doc)

            # --- Detect scanned PDF ---
            is_scanned = False
            if page_count > 0:
                avg_chars = len(raw_text.strip()) / page_count
                if avg_chars < _SCANNED_CHAR_THRESHOLD:
                    is_scanned = True
                    logger.warning(
                        "PDF appears to be scanned (avg %.0f chars/page). "
                        "Text extraction may be incomplete. Consider running OCR.",
                        avg_chars,
                    )

            # --- Detect embedded images ---
            has_images = self._detect_images(doc)

            # --- Clean text ---
            cleaned_text = self._clean_text(raw_text)

            # --- Identify sections ---
            sections = self._identify_sections(cleaned_text)

            # --- Extract PDF metadata ---
            metadata = self._extract_metadata(doc, file_path)

        finally:
            doc.close()

        report = ParsedReport(
            full_text=cleaned_text,
            sections=sections,
            page_count=page_count,
            has_images=has_images,
            is_scanned=is_scanned,
            metadata=metadata,
        )

        logger.info(
            "PDF parsed — pages=%d, sections=%d, scanned=%s, has_images=%s",
            page_count,
            len(sections),
            is_scanned,
            has_images,
        )

        return report

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _extract_text(self, doc: fitz.Document) -> str:
        """Extract text from every page, concatenated with page separators.

        Parameters
        ----------
        doc : fitz.Document
            Open PyMuPDF document.

        Returns
        -------
        str
            Raw extracted text.
        """
        page_texts: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                # Use "text" extraction which preserves layout better than "rawdict"
                text = page.get_text("text")
            except Exception as exc:
                logger.warning(
                    "Failed to extract text from page %d: %s", page_num + 1, exc,
                )
                text = ""
            page_texts.append(text)

        return "\n\n".join(page_texts)

    def _identify_sections(self, text: str) -> dict[str, str]:
        """Identify structured sections in the report text.

        We scan for known heading patterns, record their positions, and
        extract the text between consecutive headings as section content.

        Parameters
        ----------
        text : str
            Cleaned report text.

        Returns
        -------
        dict[str, str]
            Mapping of canonical section name → section body text.
        """
        if not text.strip():
            return {}

        # Collect (start_pos, end_of_heading_pos, section_name) tuples
        found_headings: list[tuple[int, int, str]] = []

        for section_name, pattern in _SECTION_PATTERNS.items():
            for match in pattern.finditer(text):
                found_headings.append(
                    (match.start(), match.end(), section_name)
                )

        if not found_headings:
            logger.debug("No standard sections identified in report text.")
            # Return the entire text as an 'unstructured' section
            return {"unstructured": text.strip()}

        # Sort by position in the document
        found_headings.sort(key=lambda h: h[0])

        sections: dict[str, str] = {}

        for idx, (start, heading_end, section_name) in enumerate(found_headings):
            # Section body extends from end of heading to start of next heading
            if idx + 1 < len(found_headings):
                body_end = found_headings[idx + 1][0]
            else:
                body_end = len(text)

            body = text[heading_end:body_end].strip()

            # If the same canonical section appears multiple times, append
            if section_name in sections:
                sections[section_name] += "\n\n" + body
            else:
                sections[section_name] = body

        # Also capture any text before the first heading as 'header'
        first_heading_start = found_headings[0][0]
        preamble = text[:first_heading_start].strip()
        if preamble:
            sections["header"] = preamble

        return sections

    def _clean_text(self, text: str) -> str:
        """Clean extracted text: normalise whitespace and line breaks.

        Parameters
        ----------
        text : str
            Raw extracted text.

        Returns
        -------
        str
            Cleaned text.
        """
        if not text:
            return ""

        # Replace form-feed and vertical tab with newlines
        text = text.replace("\f", "\n").replace("\v", "\n")

        # Normalise Windows-style line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse runs of 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Collapse runs of spaces/tabs (but NOT newlines) to a single space
        text = re.sub(r"[^\S\n]+", " ", text)

        # Strip leading/trailing whitespace on each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Strip leading/trailing whitespace overall
        text = text.strip()

        return text

    def _detect_images(self, doc: fitz.Document) -> bool:
        """Return True if any page contains embedded raster images."""
        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                image_list = page.get_images(full=True)
                if image_list:
                    return True
            except Exception:
                continue
        return False

    def _extract_metadata(
        self, doc: fitz.Document, file_path: str,
    ) -> dict[str, Any]:
        """Extract PDF-level metadata.

        Parameters
        ----------
        doc : fitz.Document
            Open PyMuPDF document.
        file_path : str
            Original file path (included for reference).

        Returns
        -------
        dict[str, Any]
        """
        raw_meta = doc.metadata or {}

        metadata: dict[str, Any] = {
            "source_file": file_path,
            "title": raw_meta.get("title", ""),
            "author": raw_meta.get("author", ""),
            "subject": raw_meta.get("subject", ""),
            "creator": raw_meta.get("creator", ""),
            "producer": raw_meta.get("producer", ""),
            "creation_date": self._parse_pdf_date(
                raw_meta.get("creationDate", "")
            ),
            "modification_date": self._parse_pdf_date(
                raw_meta.get("modDate", "")
            ),
            "page_count": len(doc),
            "pdf_version": getattr(doc, "version", None),
        }

        # Remove empty string values for cleanliness
        metadata = {
            k: v for k, v in metadata.items() if v is not None and v != ""
        }

        return metadata

    @staticmethod
    def _parse_pdf_date(date_str: str) -> str | None:
        """Parse a PDF date string like ``D:20240115120000+05'30'``
        into an ISO 8601 string.  Returns *None* on failure.
        """
        if not date_str:
            return None

        # Remove 'D:' prefix
        cleaned = date_str
        if cleaned.startswith("D:"):
            cleaned = cleaned[2:]

        # Try common formats
        for fmt in (
            "%Y%m%d%H%M%S",
            "%Y%m%d%H%M",
            "%Y%m%d",
            "%Y",
        ):
            try:
                dt = datetime.strptime(cleaned[:len(fmt.replace("%", ""))], fmt)
                return dt.isoformat()
            except (ValueError, IndexError):
                continue

        # Fallback — return the raw string
        return date_str
