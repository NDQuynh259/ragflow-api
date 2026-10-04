"""Document processing pipeline.

Orchestrates: parse → normalize → type-aware chunking → validate.

The pipeline uses OpenDataLoader as the default parser and HeadingAwareChunker
as the default chunker.  Both can be replaced via constructor injection.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from rag_document_pipeline.chunking.base import Chunker
from rag_document_pipeline.chunking.multimodal import HeadingAwareChunker
from rag_document_pipeline.models import (
    DocumentChunk,
    LayoutElement,
    ProcessedDocument,
)
from rag_document_pipeline.normalizers.layout import LayoutNormalizer
from rag_document_pipeline.parsers.base import Parser


class DocumentPipeline:
    """Layout-aware, type-specific document processing pipeline.

    Flow::

        PDF bytes
          → Parser (OpenDataLoader)
          → Normalize (Unicode NFC, mojibake repair, whitespace, caption/footnote binding)
          → Type-aware chunking (text / table / image)
          → Validate chunks
          → ProcessedDocument
    """

    def __init__(
        self,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        embed_fn: Any = None,
    ) -> None:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Invalid chunk window")

        # Default: OpenDataLoader parser
        if parser is not None:
            self.parser = parser
        else:
            self.parser = self._default_parser()

        if chunker is not None:
            self.chunker = chunker
        else:
            # The multimodal reading-order router is always used.
            self.chunker = HeadingAwareChunker.hybrid_semantic(
                embed_fn=embed_fn,
                min_chunk_size=min(300, chunk_size // 4),
                max_chunk_size=chunk_size,
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @classmethod
    def hybrid_semantic(
        cls,
        *,
        parser: Parser | None = None,
        embed_fn: Any = None,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
    ) -> DocumentPipeline:
        """Tạo DocumentPipeline cấu hình sẵn Mô hình Lai (Heading-Aware + Semantic Topic Shifts).

        Kết hợp:
        1. Gộp phần nhỏ cùng ý:
           - Hấp thụ Caption & Footnote vào Bảng biểu / Hình ảnh.
           - Giữ Bảng nhỏ inline cùng văn bản dẫn giải.
           - Lũy tiến gộp các câu ngắn trong cùng Section nếu < min_chunk_size.
        2. Cắt phần dài đổi ý:
           - Tách câu tiếng Việt chuẩn hóa (bảo vệ viết tắt, số thập phân).
           - Đo khoảng cách ngữ nghĩa qua Sliding Window Buffer.
           - Cắt ranh giới chunk mới tại điểm nhảy vọt chủ đề (threshold_percentile).
        """
        chunker = HeadingAwareChunker.hybrid_semantic(
            embed_fn=embed_fn,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            threshold_percentile=threshold_percentile,
        )
        return cls(
            parser=parser,
            chunker=chunker,
            chunk_size=max_chunk_size,
        )

    # region process
    def process(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str,
        image_dir: str | Path | None = None,
    ) -> ProcessedDocument:
        """Run the full pipeline: parse → normalize → chunk → validate."""

        # 1. Parse
        if image_dir:
            try:
                elements = self.parser.parse(content, filename=filename, image_dir=image_dir)
            except TypeError:
                elements = self.parser.parse(content, filename=filename)
        else:
            elements = self.parser.parse(content, filename=filename)

        # 2. Normalize
        elements = self._normalize(elements)

        # 3. Chunk (type-aware via HeadingAwareChunker)
        chunks = self.chunker.chunk(elements, document_id=document_id)

        # 4. Validate
        chunks = self._validate(chunks, document_id=document_id)

        return ProcessedDocument(
            document_id=document_id,
            filename=filename,
            page_count=max((el.page_number for el in elements), default=0),
            elements=elements,
            chunks=chunks,
        )

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @classmethod
    def _normalize(cls, elements: list[LayoutElement]) -> list[LayoutElement]:
        """Unicode NFC normalization, mojibake repair, whitespace cleanup, and layout binding."""
        for el in elements:
            el.text = cls._clean_text(el.text)
            if el.caption:
                el.caption = cls._clean_text(el.caption)
            if el.image_data and el.image_data.caption:
                el.image_data.caption = cls._clean_text(el.image_data.caption)

        # Bind standalone captions and footnotes to their adjacent target elements
        elements = LayoutNormalizer.bind_captions_and_footnotes(elements)
        return elements

    @staticmethod
    def _clean_text(value: str) -> str:
        """Normalize Unicode, repair mojibake, clean whitespace."""
        if not value:
            return value

        # Unicode NFC normalization
        value = unicodedata.normalize("NFC", value)

        # Remove control characters (keep newlines and tabs)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

        # Collapse excessive whitespace but preserve paragraph breaks
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)

        return value.strip()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        chunks: list[DocumentChunk],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Validate chunks and filter out invalid ones."""
        valid: list[DocumentChunk] = []
        seen_ids: set[str] = set()

        for chunk in chunks:
            # Content check
            if chunk.indexable and not chunk.content.strip():
                continue

            # Document ID consistency
            if chunk.document_id != document_id:
                chunk.document_id = document_id

            # Unique ID
            if chunk.id in seen_ids:
                import uuid

                chunk.id = str(uuid.uuid4())
            seen_ids.add(chunk.id)

            # Page bounds
            if chunk.page_start > chunk.page_end:
                chunk.page_start, chunk.page_end = (
                    chunk.page_end,
                    chunk.page_start,
                )

            valid.append(chunk)

        # Re-index
        for idx, chunk in enumerate(valid):
            chunk.index = idx

        return valid

    # ------------------------------------------------------------------
    # Default parser selection
    # ------------------------------------------------------------------

    @staticmethod
    def _default_parser() -> Parser:
        """Choose parser based on PARSER_PROVIDER env var or default to OpenDataLoader."""
        from rag_document_pipeline.parsers.opendataloader import (
            OpenDataLoaderParser,
        )

        return OpenDataLoaderParser()
