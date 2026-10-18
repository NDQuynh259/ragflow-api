"""Chính sách phân đoạn văn bản nhận biết cấu trúc mục lục (Structure-Aware Text Policy).

Kế thừa `TextChunker` nhằm duy trì tên gọi tương thích với kiến trúc phân cấp chính sách phân đoạn.
Tôn trọng ranh giới các cấp tiêu đề Heading và gộp các đoạn văn nhỏ trong cùng một mục.
"""

from __future__ import annotations

from rag_document_pipeline.chunking.strategies.text import TextChunker


class StructureAwareTextPolicy(TextChunker):
    """Tên tương thích (Alias) cho bộ băm văn bản nhận biết cấu trúc mục lục (TextChunker)."""


__all__ = ["StructureAwareTextPolicy"]
