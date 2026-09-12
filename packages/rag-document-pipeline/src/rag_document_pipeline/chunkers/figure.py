"""Image/figure chunker.

Images with captions or descriptions become indexable chunks.
Images without any textual representation are kept as metadata-only
records (``indexable=False``) so they are not embedded as empty strings.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from rag_document_pipeline.chunkers.base import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class ImageChunker:
    """Chunk image/figure elements based on available textual content."""

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        for el in elements:
            chunks.append(self._chunk_image(el, document_id=document_id))

        return chunks

    @staticmethod
    def _chunk_image(
        element: LayoutElement,
        *,
        document_id: str,
    ) -> DocumentChunk:
        parts: list[str] = ["[IMAGE]"]
        img = element.image_data

        caption = (img.caption if img else None) or element.caption or ""
        description = img.description if img else None
        ocr_text = img.ocr_text if img else None

        if caption:
            parts.append(caption)
        if description:
            parts.append(description)
        if ocr_text:
            parts.append(ocr_text)

        # Also include any element text that isn't already covered
        if element.text.strip() and element.text.strip() not in parts:
            parts.append(element.text.strip())

        if len(parts) <= 1 and img and img.uri:
            parts.append(f"Visual image/diagram on page {element.page_number} ({Path(img.uri).name})")

        has_content = len(parts) > 1  # more than just "[IMAGE]"
        content = "\n".join(parts)

        metadata: dict = {
            "chunker": "image",
            "image_available": True,
        }
        if img and img.uri:
            metadata["image_uri"] = img.uri
        if not has_content:
            metadata["index_reason"] = "no_caption_or_description"

        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            content=content if has_content else f"[IMAGE] Visual on page {element.page_number}",
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
