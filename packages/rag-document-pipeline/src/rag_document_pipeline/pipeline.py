"""Document processing pipeline.

Orchestrates: parse → normalize → type-aware chunking → validate.

The pipeline uses OpenDataLoader as the default parser and MultimodalChunker
as the default chunker.  Both can be replaced via constructor injection.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_document_pipeline.chunking.core import Chunker
from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.models import (
    DocumentChunk,
    LayoutElement,
    ProcessedDocument,
)
from rag_document_pipeline.normalizers.layout import LayoutNormalizer
from rag_document_pipeline.parsers.base import Parser


@dataclass(frozen=True)
class ChunkingProfile:
    chunk_size: int
    threshold_percentile: float | None = None


CHUNKING_PROFILES = {
    "internal": ChunkingProfile(chunk_size=1200, threshold_percentile=80.0),
    "business_plan": ChunkingProfile(chunk_size=1500),
    "progress_report": ChunkingProfile(chunk_size=1500),
    "legal_policy": ChunkingProfile(chunk_size=2000),
    "guide_sop": ChunkingProfile(chunk_size=1500),
}

DOCUMENT_TYPE_PATTERNS = {
    "legal_policy": re.compile(
        r"\b(chương|điều khoản|điều|khoản|căn cứ|quy định|hợp đồng|terms of service|liability)\b",
        re.I,
    ),
    "guide_sop": re.compile(
        r"\b(hướng dẫn|quy trình|thao tác|bước\s+\d+|cảnh báo|sop|user guide)\b", re.I
    ),
    "progress_report": re.compile(
        r"\b(báo cáo tiến độ|kỳ báo cáo|milestone|sprint|kpi|tiến độ|hoàn thành)\b", re.I
    ),
    "business_plan": re.compile(
        r"\b(kế hoạch kinh doanh|business plan|ngân sách|doanh thu|giả định|mục tiêu chiến lược)\b",
        re.I,
    ),
}


def normalize_document_type(document_type: str | None) -> str | None:
    if not document_type:
        return None
    normalized = re.sub(r"[\s-]+", "_", document_type.strip().lower())
    aliases = {
        "internal": "internal",
        "general_internal": "internal",
        "business": "business_plan",
        "business_plan": "business_plan",
        "progress": "progress_report",
        "progress_report": "progress_report",
        "legal": "legal_policy",
        "policy": "legal_policy",
        "legal_policy": "legal_policy",
        "guide": "guide_sop",
        "sop": "guide_sop",
        "guide_sop": "guide_sop",
    }
    return aliases.get(normalized)


def infer_document_type(elements: list[LayoutElement]) -> str:
    headings = " ".join(el.text for el in elements if el.type.lower() == "heading")
    text = " ".join(el.text for el in elements if el.type.lower() not in {"header", "footer"})
    scores: dict[str, int] = {}
    for kind, pattern in DOCUMENT_TYPE_PATTERNS.items():
        scores[kind] = 2 * len(pattern.findall(headings)) + len(pattern.findall(text))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < 3 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return "internal"
    return ranked[0][0]


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
        embed_fn: Any = None,
        vision_fn: Any = None,
        triage_enabled: bool = True,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        # Default: OpenDataLoader parser
        if parser is not None:
            self.parser = parser
        else:
            self.parser = self._default_parser()

        if chunker is not None:
            self.chunker = chunker
        else:
            # The multimodal reading-order router is always used.
            self.chunker = MultimodalChunker(
                embed_fn=embed_fn,
                vision_fn=vision_fn,
                triage_enabled=triage_enabled,
                min_chunk_size=min(300, chunk_size // 4),
                max_chunk_size=chunk_size,
            )
        self.chunk_size = chunk_size

    @classmethod
    def hybrid_semantic(
        cls,
        *,
        parser: Parser | None = None,
        embed_fn: Any = None,
        vision_fn: Any = None,
        triage_enabled: bool = True,
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
        3. Xử lý đa phương tiện:
           - Sử dụng duy nhất `vision_fn` (VLM) cho toàn bộ hình ảnh hợp lệ.
        """
        chunker = MultimodalChunker(
            embed_fn=embed_fn,
            vision_fn=vision_fn,
            triage_enabled=triage_enabled,
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
        document_type: str | None = None,
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

        # 3. Chunk using an explicit type or infer a conservative document profile.
        explicit_type = normalize_document_type(document_type)
        resolved_type = explicit_type or infer_document_type(elements)
        profile = CHUNKING_PROFILES[resolved_type]
        if explicit_type is None and resolved_type == "internal":
            profile = ChunkingProfile(
                chunk_size=self.chunk_size,
                threshold_percentile=profile.threshold_percentile,
            )
        if isinstance(self.chunker, MultimodalChunker):
            chunks = self.chunker.chunk(
                elements,
                document_id=document_id,
                chunk_size=profile.chunk_size,
                threshold_percentile=profile.threshold_percentile,
                semantic_enabled=resolved_type == "internal",
            )
        else:
            chunks = self.chunker.chunk(elements, document_id=document_id)
        for chunk in chunks:
            chunk.metadata.setdefault("document_type", resolved_type)
            chunk.metadata.setdefault("chunk_size_chars", profile.chunk_size)
            chunk.metadata.setdefault("semantic_chunking", resolved_type == "internal")

        # 4. Validate
        chunks = self._validate(chunks, document_id=document_id)

        return ProcessedDocument(
            document_id=document_id,
            filename=filename,
            page_count=max((el.page_number for el in elements), default=0),
            elements=elements,
            chunks=chunks,
        )

    #region _normalize
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

    #region _clean_text
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

    #region _validate
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
                from core.uuid7 import uuid7_str

                chunk.id = uuid7_str()
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

    # region _default_parser
    @staticmethod
    def _default_parser() -> Parser:
        """Choose parser based on PARSER_PROVIDER env var or default to OpenDataLoader."""
        from rag_document_pipeline.parsers.opendataloader import (
            OpenDataLoaderParser,
        )

        return OpenDataLoaderParser()
