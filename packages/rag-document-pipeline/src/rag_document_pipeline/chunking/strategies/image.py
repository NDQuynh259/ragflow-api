"""Image/figure chunker.

Images with captions or descriptions become indexable chunks.
Images without any textual representation are kept as metadata-only
records (``indexable=False``) so they are not embedded as empty strings.

OCR extraction is bounded by max_ocr_length (default: 2000 characters).

Two optional callbacks are supported:

* ``ocr_fn`` — transcribes visible text (used for scanned text, invoices).
* ``vision_fn`` — produces a structured semantic analysis of charts and
  diagrams. It is tried when the image looks semantic (large, little text)
  and OCR alone would lose the meaning of the figure.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from rag_document_pipeline.chunking.core import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement

logger = logging.getLogger(__name__)

DEFAULT_MAX_OCR_LENGTH = 2000

#: Images smaller than this (in points or pixels) are considered decorative.
DEFAULT_MIN_IMAGE_SIZE = 100
#: An aspect ratio beyond this is treated as a rule/divider line, not a figure.
DEFAULT_MAX_ASPECT_RATIO = 10.0
#: Images at least this large with little OCR text are treated as semantic
#: figures (charts, diagrams) that warrant a vision analysis call.
DEFAULT_VISION_MIN_SIZE = 400
#: Below this many OCR characters a large image is assumed to be a chart.
DEFAULT_VISION_MAX_TEXT = 80


class ImageChunker:
    """Chunk image/figure elements based on available textual content."""

    def __init__(
        self,
        *,
        ocr_fn: Any = None,
        vision_fn: Any = None,
        max_ocr_length: int = DEFAULT_MAX_OCR_LENGTH,
        triage_enabled: bool = True,
        min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        vision_min_size: int = DEFAULT_VISION_MIN_SIZE,
        vision_max_text: int = DEFAULT_VISION_MAX_TEXT,
    ) -> None:
        self.ocr_fn = ocr_fn
        self.vision_fn = vision_fn
        self.max_ocr_length = max_ocr_length
        self.triage_enabled = triage_enabled
        self.min_image_size = min_image_size
        self.max_aspect_ratio = max_aspect_ratio
        self.vision_min_size = vision_min_size
        self.vision_max_text = vision_max_text

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        for el in elements:
            chunks.append(self._chunk_image(el, document_id=document_id, workspace_id=workspace_id))

        return chunks

    # region triage
    def _image_dimensions(self, element: LayoutElement) -> tuple[float, float] | None:
        """Return the image's width and height, preferring real pixel dimensions.

        Parsers may record intrinsic pixel sizes in ``metadata``; otherwise the
        layout bbox is used as a proxy in PDF points.
        """
        width = element.metadata.get("width") or element.metadata.get("image_width")
        height = element.metadata.get("height") or element.metadata.get("image_height")
        try:
            if width and height:
                return float(width), float(height)
        except (TypeError, ValueError):
            logger.warning("Ignoring non-numeric image dimensions on element %s", element.id)

        if element.bbox:
            x0, y0, x1, y1 = element.bbox
            return abs(x1 - x0), abs(y1 - y0)
        return None

    def _triage_skip_reason(self, element: LayoutElement) -> str | None:
        """Return why an image should be skipped, or ``None`` to keep it."""
        if not self.triage_enabled:
            return None
        dimensions = self._image_dimensions(element)
        if dimensions is None:
            return None
        width, height = dimensions
        if width <= 0 or height <= 0:
            return "invalid_dimensions"
        if width < self.min_image_size or height < self.min_image_size:
            return "too_small"
        aspect_ratio = max(width / height, height / width)
        if aspect_ratio > self.max_aspect_ratio:
            return "extreme_aspect_ratio"
        return None

    def _is_semantic_figure(self, element: LayoutElement, ocr_text: str | None) -> bool:
        """Return ``True`` when the image is large but carries little text."""
        if not self.vision_fn:
            return False
        dimensions = self._image_dimensions(element)
        if dimensions is None:
            return False
        width, height = dimensions
        if min(width, height) < self.vision_min_size:
            return False
        return len((ocr_text or "").strip()) < self.vision_max_text

    def _decorative_chunk(
        self,
        element: LayoutElement,
        *,
        skip_reason: str,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        """Build a non-indexed metadata record for a decorative image."""
        img = element.image_data
        metadata: dict[str, Any] = {
            "chunker": "image",
            "modality": "image",
            "image_available": bool(img and img.uri),
            "triage_skipped": True,
            "triage_skip_reason": skip_reason,
            "index_reason": skip_reason,
        }
        if img and img.uri:
            metadata["image_uri"] = img.uri

        content = "[IMAGE]"
        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            workspace_id=workspace_id,
            content=content,
            index=0,
            page_start=element.page_number,
            page_end=element.page_number,
            element_ids=[element.id],
            bboxes=[element.bbox] if element.bbox else [],
            kind="figure",
            section_path=element.section_path,
            token_count=0,
            indexable=False,
            metadata=metadata,
        )

    def _run_callback(
        self,
        callback: Any,
        image_source: str,
        *,
        element: LayoutElement,
        metadata: dict[str, Any],
        label: str,
    ) -> str | None:
        """Invoke OCR/vision callback, bounded by max_ocr_length, failure-safe."""
        try:
            extracted = callback(image_source)
        except Exception as exc:
            logger.warning("%s extraction failed for %s: %s", label, image_source, exc)
            metadata[f"{label.lower()}_error"] = str(exc)
            return None

        if not extracted or not isinstance(extracted, str) or not extracted.strip():
            return None

        text = extracted.strip()
        if len(text) > self.max_ocr_length:
            logger.warning(
                "%s text for element %s exceeds max_ocr_length (%d), truncating",
                label,
                element.id,
                self.max_ocr_length,
            )
            text = text[: self.max_ocr_length]
            metadata[f"{label.lower()}_truncated"] = True
        return text

    # region _chunk_image
    def _chunk_image(
        self,
        element: LayoutElement,
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        parts: list[str] = ["[IMAGE]"]
        img = element.image_data

        caption = (img.caption if img else None) or element.caption or ""
        description = img.description if img else None

        # 0. Image triage: drop decorative/degenerate images before paying for OCR.
        skip_reason = self._triage_skip_reason(element)
        if skip_reason:
            return self._decorative_chunk(
                element,
                skip_reason=skip_reason,
                document_id=document_id,
                workspace_id=workspace_id,
            )

        # 1. Check OCR text from ImageData, element metadata, or element text
        ocr_text = (
            (img.ocr_text if img else None)
            or element.metadata.get("ocr_text")
            or element.metadata.get("ocr")
        )

        metadata: dict[str, Any] = {
            "chunker": "image",
            "modality": "image",
            "image_available": True,
        }
        if self.ocr_fn:
            metadata["ocr_attempted"] = False

        image_source = (
            (img.uri if img else None)
            or element.source
            or element.metadata.get("image_path")
            or element.metadata.get("uri")
        )

        if not ocr_text and self.ocr_fn and image_source:
            metadata["ocr_attempted"] = True
            ocr_text = self._run_callback(
                self.ocr_fn,
                image_source,
                element=element,
                metadata=metadata,
                label="OCR",
            )
            if ocr_text and img:
                img.ocr_text = ocr_text
            if ocr_text:
                element.metadata["ocr_text"] = ocr_text

        # 2. Structured vision analysis for charts and diagrams, where OCR text
        #    alone would strip the figure of its meaning.
        if image_source and self._is_semantic_figure(element, ocr_text):
            metadata["vision_attempted"] = True
            analysis = self._run_callback(
                self.vision_fn,
                image_source,
                element=element,
                metadata=metadata,
                label="Vision",
            )
            if analysis:
                if ocr_text:
                    metadata["ocr_text"] = ocr_text
                ocr_text = analysis
                metadata["has_vision_analysis"] = True
                if img:
                    img.description = analysis

        if caption:
            parts.append(caption)
        if description:
            parts.append(description)
        if ocr_text:
            parts.append(f"OCR: {ocr_text}" if not ocr_text.lower().startswith("ocr:") else ocr_text)

        # Also include any element text that isn't already covered
        if element.text.strip() and element.text.strip() not in parts:
            parts.append(element.text.strip())

        footnote = element.metadata.get("footnote")
        if footnote:
            parts.append(f"Note: {footnote}")

        has_content = len(parts) > 1  # more than just "[IMAGE]"
        content = "\n".join(parts)

        if img and img.uri:
            metadata["image_uri"] = img.uri
        if ocr_text:
            metadata["has_ocr"] = True
            metadata["ocr_text"] = ocr_text
        if not has_content:
            metadata["index_reason"] = "no_caption_or_description"

        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            workspace_id=workspace_id,
            content=content,
            index=0,
            page_start=element.page_number,
            page_end=element.page_number,
            element_ids=[element.id],
            bboxes=[element.bbox] if element.bbox else [],
            kind="figure",
            section_path=element.section_path,
            token_count=estimate_tokens(content) if has_content else 0,
            indexable=has_content,
            metadata=metadata,
        )


__all__ = ["ImageChunker"]
