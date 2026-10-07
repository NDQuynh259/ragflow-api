"""Image/figure chunker.

Images with captions or descriptions become indexable chunks.
Images without any textual representation are kept as metadata-only
records (``indexable=False``) so they are not embedded as empty strings.
"""

from __future__ import annotations

import uuid
from typing import Any

from rag_document_pipeline.chunking.core import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class ImageChunker:
    """Chunk image/figure elements based on available textual content."""

    def __init__(self, *, ocr_fn: Any = None) -> None:
        self.ocr_fn = ocr_fn

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

        # 1. Check OCR text from ImageData, element metadata, or element text
        ocr_text = (
            (img.ocr_text if img else None)
            or element.metadata.get("ocr_text")
            or element.metadata.get("ocr")
        )

        # 2. If OCR is missing and ocr_fn is provided, extract OCR from image source
        if not ocr_text and self.ocr_fn:
            image_source = (
                (img.uri if img else None)
                or element.source
                or element.metadata.get("image_path")
                or element.metadata.get("uri")
            )
            if image_source:
                try:
                    extracted = self.ocr_fn(image_source)
                    if extracted and isinstance(extracted, str) and extracted.strip():
                        ocr_text = extracted.strip()
                        if img:
                            img.ocr_text = ocr_text
                        element.metadata["ocr_text"] = ocr_text
                except Exception:
                    pass

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

        metadata: dict = {
            "chunker": "image",
            "modality": "image",
            "image_available": True,
        }
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

