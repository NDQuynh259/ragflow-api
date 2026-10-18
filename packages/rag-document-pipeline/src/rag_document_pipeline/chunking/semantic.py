"""Chính sách phân đoạn ngữ nghĩa (Semantic Splitting Policy).

Đóng gói cấu hình phân tách ngữ nghĩa (dựa trên khoảng cách cosine embedding giữa các câu)
thành một chính sách tường minh mà không cần thay đổi engine băm cốt lõi.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag_document_pipeline.chunking.strategies.text import TextChunker


@dataclass(frozen=True)
class SemanticPolicy:
    """Chính sách điều khiển tính năng phân tách theo ngữ nghĩa (Semantic Chunking).

    Attributes:
        enabled: Cờ bật/tắt thuật toán phân tách theo bước nhảy chủ đề (topic shift).
    """

    enabled: bool = False

    def configure(self, chunker: TextChunker) -> TextChunker:
        """Tạo một bản sao của TextChunker đã được thiết lập cờ `semantic_enabled` theo chính sách này.

        Args:
            chunker: Thể hiện TextChunker gốc.

        Returns:
            TextChunker: Thể hiện TextChunker mới với cấu hình semantic_enabled đã cập nhật.
        """
        return TextChunker(
            embed_fn=chunker.embed_fn,
            min_chunk_size=chunker.min_chunk_size,
            max_chunk_size=chunker.max_chunk_size,
            threshold_percentile=chunker.threshold_percentile,
            window_size=chunker.window_size,
            semantic_enabled=self.enabled,
        )


__all__ = ["SemanticPolicy"]
