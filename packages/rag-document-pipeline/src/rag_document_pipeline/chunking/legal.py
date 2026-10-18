"""Chính sách phân đoạn văn bản pháp lý & hợp đồng (Legal Policy).

Tái xuất `LegalHierarchyChunker` và `LegalHierarchyConfig` dưới tên `LegalPolicy` nhằm duy trì
cấu trúc phân cấp Điều (Article) - Khoản (Clause) - Điểm (Point), không ngắt cụt điều khoản pháp lý.
"""

from rag_document_pipeline.chunking.strategies.legal import (
    LegalHierarchyChunker,
    LegalHierarchyConfig,
)

LegalPolicy = LegalHierarchyChunker

__all__ = ["LegalHierarchyChunker", "LegalHierarchyConfig", "LegalPolicy"]
