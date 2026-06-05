"""
Medical Image Processing Service
================================

Comprehensive image preprocessing pipeline for medical imaging analysis.
Supports DICOM files (with windowing presets), standard images (JPEG/PNG),
and provides enhancement via CLAHE and aspect-ratio-preserving resize.

All processed images are returned as PIL Images suitable for upload to
the Gemini multimodal API.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUPPORTED_STANDARD_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
_DICOM_EXTENSIONS = {".dcm", ".dicom"}

# Minimum text-to-pixel ratio to consider a DICOM file valid
_MIN_PIXEL_AREA = 16  # 4x4 at minimum


class OriginalFormat(str, Enum):
    """Enumeration of supported original file formats."""
    DICOM = "dicom"
    JPEG = "jpeg"
    PNG = "png"
    BMP = "bmp"
    TIFF = "tiff"
    WEBP = "webp"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ProcessedImage(BaseModel):
    """Container for a fully-processed medical image and its metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: Image.Image = Field(
        ...,
        description="Processed PIL Image ready for Gemini upload.",
    )
    image_path: str = Field(
        ...,
        description="Absolute path to the saved processed image on disk.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted metadata (modality, dimensions, patient info, file format, etc.).",
    )
    original_format: str = Field(
        ...,
        description="Original file format: 'dicom', 'jpeg', 'png', etc.",
    )


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class ImageProcessor:
    """Medical image preprocessing pipeline.

    Handles DICOM and standard image files, applies appropriate
    enhancement and normalisation, and produces a *ProcessedImage*
    ready for downstream AI analysis.

    Parameters
    ----------
    target_size : int
        Target dimension (longest edge) for the output image.
        The image is resized while maintaining aspect ratio and
        padded to a square canvas of ``target_size × target_size``.
    output_dir : str | None
        Directory to write processed images.  Defaults to the
        system temporary directory.
    """

    # Pre-configured radiology windowing presets
    WINDOW_PRESETS: dict[str, dict[str, int]] = {
        "lung": {"width": 1500, "center": -600},
        "bone": {"width": 2000, "center": 300},
        "soft_tissue": {"width": 400, "center": 40},
        "brain": {"width": 80, "center": 40},
    }

    def __init__(
        self,
        target_size: int = 1024,
        output_dir: str | None = None,
    ) -> None:
        if target_size < 64:
            raise ValueError("target_size must be >= 64")
        self.target_size = target_size
        self.output_dir = output_dir or tempfile.gettempdir()
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(
            "ImageProcessor initialised — target_size=%d, output_dir=%s",
            self.target_size,
            self.output_dir,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        file_path: str,
        window_preset: str | None = None,
    ) -> ProcessedImage:
        """Main entry point — detect file type and route to the appropriate processor.

        Parameters
        ----------
        file_path : str
            Path to the input image or DICOM file.
        window_preset : str | None
            Optional windowing preset for DICOM files.  One of
            ``'lung'``, ``'bone'``, ``'soft_tissue'``, ``'brain'``,
            or *None* for automatic/default windowing.

        Returns
        -------
        ProcessedImage
            Processed image container with metadata.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        ValueError
            If the file format is unsupported or the image is corrupt.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        ext = path.suffix.lower()
        logger.info("Processing file: %s (extension=%s)", path.name, ext)

        if ext in _DICOM_EXTENSIONS or self._is_dicom_by_magic(file_path):
            return self._process_dicom(file_path, window_preset=window_preset)
        elif ext in _SUPPORTED_STANDARD_FORMATS:
            return self._process_standard_image(file_path)
        else:
            # Attempt standard image load as a fallback
            logger.warning(
                "Unrecognised extension '%s' — attempting standard image load.", ext,
            )
            try:
                return self._process_standard_image(file_path)
            except Exception:
                raise ValueError(
                    f"Unsupported or unreadable file format: '{ext}' for {file_path}"
                )

    # ------------------------------------------------------------------
    # DICOM processing
    # ------------------------------------------------------------------

    def _process_dicom(
        self,
        file_path: str,
        window_preset: str | None = None,
    ) -> ProcessedImage:
        """Load a DICOM file, extract metadata, apply windowing, and convert to image.

        Parameters
        ----------
        file_path : str
            Path to DICOM file.
        window_preset : str | None
            Windowing preset name or *None* for auto.

        Returns
        -------
        ProcessedImage
        """
        try:
            import pydicom
            from pydicom.errors import InvalidDicomError
        except ImportError as exc:
            raise ImportError(
                "pydicom is required for DICOM processing. "
                "Install it with: pip install pydicom"
            ) from exc

        logger.info("Loading DICOM file: %s", file_path)

        try:
            ds = pydicom.dcmread(file_path, force=True)
        except (InvalidDicomError, Exception) as exc:
            logger.error("Failed to read DICOM file %s: %s", file_path, exc)
            raise ValueError(f"Corrupted or invalid DICOM file: {file_path}") from exc

        # --- Extract metadata ---
        metadata = self._extract_dicom_metadata(ds, file_path)

        # --- Get pixel data ---
        if not hasattr(ds, "PixelData") and not hasattr(ds, "pixel_array"):
            raise ValueError(
                f"DICOM file has no pixel data: {file_path}. "
                "This may be a structured report or secondary capture without image data."
            )

        try:
            pixel_array = ds.pixel_array.astype(np.float64)
        except Exception as exc:
            raise ValueError(
                f"Unable to decompress or read pixel data from DICOM file: {file_path}. "
                f"Transfer syntax may be unsupported. Error: {exc}"
            ) from exc

        if pixel_array.size < _MIN_PIXEL_AREA:
            raise ValueError(
                f"DICOM pixel data too small ({pixel_array.shape}) — possibly corrupt."
            )

        # --- Apply rescale slope / intercept ---
        rescale_slope = float(getattr(ds, "RescaleSlope", 1))
        rescale_intercept = float(getattr(ds, "RescaleIntercept", 0))
        pixel_array = pixel_array * rescale_slope + rescale_intercept

        # --- Apply windowing ---
        if window_preset and window_preset in self.WINDOW_PRESETS:
            preset = self.WINDOW_PRESETS[window_preset]
            logger.info("Applying '%s' window preset.", window_preset)
            pixel_array = self._apply_windowing(
                pixel_array, center=preset["center"], width=preset["width"],
            )
            metadata["window_preset"] = window_preset
        elif window_preset == "auto" or window_preset is None:
            # Try DICOM-embedded window settings, fall back to min/max
            wc = getattr(ds, "WindowCenter", None)
            ww = getattr(ds, "WindowWidth", None)
            if wc is not None and ww is not None:
                # Handle multi-valued window center/width
                center = float(wc[0]) if isinstance(wc, pydicom.multival.MultiValue) else float(wc)
                width = float(ww[0]) if isinstance(ww, pydicom.multival.MultiValue) else float(ww)
                logger.info(
                    "Using DICOM-embedded window: center=%.1f, width=%.1f",
                    center, width,
                )
                pixel_array = self._apply_windowing(pixel_array, center=center, width=width)
                metadata["window_center"] = center
                metadata["window_width"] = width
            else:
                # Fallback: linear stretch
                logger.info("No window info — using min/max linear stretch.")
                pmin, pmax = float(np.min(pixel_array)), float(np.max(pixel_array))
                if pmax - pmin > 0:
                    pixel_array = (pixel_array - pmin) / (pmax - pmin) * 255.0
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.float64)
        else:
            raise ValueError(
                f"Unknown window preset '{window_preset}'. "
                f"Available presets: {list(self.WINDOW_PRESETS.keys())}"
            )

        # --- Handle photometric interpretation ---
        photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2")).upper()
        if photometric == "MONOCHROME1":
            # Invert: MONOCHROME1 = high values are dark
            pixel_array = 255.0 - pixel_array
            logger.debug("Inverted MONOCHROME1 pixel data.")

        # Clip to [0, 255] and convert
        pixel_array = np.clip(pixel_array, 0, 255).astype(np.uint8)

        # Handle multi-frame or colour DICOM
        if pixel_array.ndim == 3 and pixel_array.shape[2] in (3, 4):
            # Already colour
            image_array = pixel_array
        elif pixel_array.ndim == 3:
            # Multi-frame — take the first frame
            logger.info("Multi-frame DICOM detected; using first frame.")
            image_array = pixel_array[0]
            if image_array.ndim == 2:
                image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)
        elif pixel_array.ndim == 2:
            image_array = cv2.cvtColor(pixel_array, cv2.COLOR_GRAY2RGB)
        else:
            raise ValueError(
                f"Unexpected pixel_array dimensions: {pixel_array.shape}"
            )

        # --- CLAHE enhancement ---
        image_array = self._apply_clahe(image_array)

        # --- Resize ---
        image_array = self._resize_with_padding(image_array)

        # --- Build output ---
        pil_image = Image.fromarray(image_array, "RGB")
        output_path = self._save_image(pil_image)
        metadata["processed_size"] = list(pil_image.size)

        return ProcessedImage(
            image=pil_image,
            image_path=output_path,
            metadata=metadata,
            original_format=OriginalFormat.DICOM.value,
        )

    def _extract_dicom_metadata(self, ds: Any, file_path: str) -> dict[str, Any]:
        """Safely extract common DICOM tags into a plain dict."""

        def _safe(attr: str, default: Any = None) -> Any:
            val = getattr(ds, attr, default)
            if val is None:
                return default
            # Convert pydicom types to JSON-serialisable Python types
            try:
                if hasattr(val, "original_string"):
                    return str(val)
                return str(val)
            except Exception:
                return default

        metadata: dict[str, Any] = {
            "source_file": os.path.basename(file_path),
            "patient_id": "[REDACTED FOR HIPAA COMPLIANCE]",
            "patient_name": "[REDACTED FOR HIPAA COMPLIANCE]",
            "patient_birth_date": "[REDACTED FOR HIPAA COMPLIANCE]",
            "patient_sex": _safe("PatientSex"),
            "study_date": _safe("StudyDate"),
            "study_description": _safe("StudyDescription"),
            "series_description": _safe("SeriesDescription"),
            "modality": _safe("Modality"),
            "institution_name": _safe("InstitutionName"),
            "manufacturer": _safe("Manufacturer"),
            "rows": int(getattr(ds, "Rows", 0)),
            "columns": int(getattr(ds, "Columns", 0)),
            "bits_stored": int(getattr(ds, "BitsStored", 0)),
            "photometric_interpretation": _safe("PhotometricInterpretation"),
            "transfer_syntax_uid": str(getattr(ds.file_meta, "TransferSyntaxUID", "unknown"))
            if hasattr(ds, "file_meta") else "unknown",
        }
        return metadata

    # ------------------------------------------------------------------
    # Standard image processing
    # ------------------------------------------------------------------

    def _process_standard_image(self, file_path: str) -> ProcessedImage:
        """Load and process a standard (JPEG / PNG / BMP / TIFF / WEBP) image.

        Parameters
        ----------
        file_path : str
            Path to the image file.

        Returns
        -------
        ProcessedImage
        """
        logger.info("Loading standard image: %s", file_path)

        try:
            pil_img = Image.open(file_path)
            pil_img.verify()  # verify integrity
            pil_img = Image.open(file_path)  # re-open after verify
        except Exception as exc:
            raise ValueError(
                f"Unable to open image file: {file_path}. Error: {exc}"
            ) from exc

        # Validate dimensions
        width, height = pil_img.size
        if width < 4 or height < 4:
            raise ValueError(
                f"Image too small ({width}x{height}). Minimum 4×4 pixels required."
            )
        if width > 65536 or height > 65536:
            raise ValueError(
                f"Image too large ({width}x{height}). Maximum 65536×65536 pixels."
            )

        # Determine original format
        fmt = (pil_img.format or Path(file_path).suffix.lstrip(".")).lower()
        if fmt in ("jpg", "jpeg"):
            original_format = OriginalFormat.JPEG.value
        elif fmt == "png":
            original_format = OriginalFormat.PNG.value
        elif fmt == "bmp":
            original_format = OriginalFormat.BMP.value
        elif fmt in ("tiff", "tif"):
            original_format = OriginalFormat.TIFF.value
        elif fmt == "webp":
            original_format = OriginalFormat.WEBP.value
        else:
            original_format = OriginalFormat.UNKNOWN.value

        # Convert to numpy RGB
        if pil_img.mode == "L":
            # Grayscale — convert to RGB
            image_array = np.array(pil_img)
            image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)
            logger.debug("Converted grayscale image to RGB.")
        elif pil_img.mode == "RGBA":
            image_array = np.array(pil_img.convert("RGB"))
        elif pil_img.mode == "P":
            image_array = np.array(pil_img.convert("RGB"))
        elif pil_img.mode == "RGB":
            image_array = np.array(pil_img)
        elif pil_img.mode in ("I", "F"):
            # 32-bit integer or float — normalise to uint8
            arr = np.array(pil_img, dtype=np.float64)
            amin, amax = arr.min(), arr.max()
            if amax - amin > 0:
                arr = ((arr - amin) / (amax - amin) * 255).astype(np.uint8)
            else:
                arr = np.zeros_like(arr, dtype=np.uint8)
            image_array = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
        else:
            # Fallback
            image_array = np.array(pil_img.convert("RGB"))

        # --- CLAHE enhancement ---
        image_array = self._apply_clahe(image_array)

        # --- Resize ---
        image_array = self._resize_with_padding(image_array)

        # --- Build output ---
        pil_result = Image.fromarray(image_array, "RGB")
        output_path = self._save_image(pil_result)

        metadata: dict[str, Any] = {
            "source_file": os.path.basename(file_path),
            "original_width": width,
            "original_height": height,
            "original_mode": pil_img.mode,
            "file_format": original_format,
            "processed_size": list(pil_result.size),
        }

        return ProcessedImage(
            image=pil_result,
            image_path=output_path,
            metadata=metadata,
            original_format=original_format,
        )

    # ------------------------------------------------------------------
    # Image manipulation helpers
    # ------------------------------------------------------------------

    def _apply_windowing(
        self,
        pixel_array: np.ndarray,
        center: float,
        width: float,
    ) -> np.ndarray:
        """Apply radiology windowing (contrast stretching) to pixel data.

        Uses the standard VOI LUT linear transform:
            lower = center - width / 2
            upper = center + width / 2
            output = clip((pixel - lower) / (upper - lower), 0, 1) * 255

        Parameters
        ----------
        pixel_array : np.ndarray
            Raw (or rescale-adjusted) pixel values.
        center : float
            Window centre (level).
        width : float
            Window width.

        Returns
        -------
        np.ndarray
            Windowed pixel values in [0, 255] as float64.
        """
        if width <= 0:
            logger.warning("Window width <= 0 (%.1f); clamping to 1.", width)
            width = 1.0

        lower = center - width / 2.0
        upper = center + width / 2.0
        windowed = np.clip((pixel_array - lower) / (upper - lower), 0.0, 1.0) * 255.0
        return windowed

    def _apply_clahe(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Operates on the L channel in LAB colour space to preserve hue
        while enhancing local contrast.

        Parameters
        ----------
        image : np.ndarray
            Input RGB image (uint8).

        Returns
        -------
        np.ndarray
            Enhanced RGB image (uint8).
        """
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)

        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)

        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)
        return result

    def _resize_with_padding(self, image: np.ndarray) -> np.ndarray:
        """Resize image to fit within ``target_size × target_size``
        while maintaining aspect ratio, then pad to a square canvas.

        Padding is black (0, 0, 0) and centered.

        Parameters
        ----------
        image : np.ndarray
            Input RGB image (uint8).

        Returns
        -------
        np.ndarray
            Resized and padded RGB image of shape
            ``(target_size, target_size, 3)`` (uint8).
        """
        h, w = image.shape[:2]
        target = self.target_size

        # Compute scale to fit longest edge into target_size
        scale = target / max(h, w)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))

        # Resize using INTER_AREA for downscale, INTER_LINEAR for upscale
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(image, (new_w, new_h), interpolation=interp)

        # Create black canvas and centre the resized image
        canvas = np.zeros((target, target, 3), dtype=np.uint8)
        y_offset = (target - new_h) // 2
        x_offset = (target - new_w) // 2
        canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

        return canvas

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_dicom_by_magic(file_path: str) -> bool:
        """Check the DICOM magic bytes (``DICM`` at offset 128).

        Returns *True* if the file appears to be a valid DICOM file
        regardless of its extension.
        """
        try:
            with open(file_path, "rb") as fh:
                fh.seek(128)
                return fh.read(4) == b"DICM"
        except Exception:
            return False

    def _save_image(self, pil_image: Image.Image) -> str:
        """Save a PIL Image to disk as PNG and return the file path."""
        filename = f"processed_{uuid.uuid4().hex[:12]}.png"
        output_path = os.path.join(self.output_dir, filename)
        pil_image.save(output_path, format="PNG", optimize=True)
        logger.info("Saved processed image to: %s", output_path)
        return output_path
