"""Mô-đun định tuyến và phân loại tài liệu (Classification & Adaptive Chunk Routing).

Cung cấp các cơ chế phân loại tài liệu và section theo 3 tầng (classifier),
và bộ định tuyến băm thích ứng `AdaptiveChunkingRouter` cùng cấu hình `ChunkingProfile`.
"""

from .chunking_router import CHUNKING_PROFILES, AdaptiveChunkingRouter, ChunkingProfile
from .classifier import (
    DOCUMENT_TYPE_ALIASES,
    DOCUMENT_TYPE_PATTERNS,
    DocumentType,
    classify_document,
    classify_section,
    infer_document_type,
    normalize_document_type,
)

__all__ = [
    "CHUNKING_PROFILES",
    "DOCUMENT_TYPE_ALIASES",
    "DOCUMENT_TYPE_PATTERNS",
    "AdaptiveChunkingRouter",
    "ChunkingProfile",
    "DocumentType",
    "classify_document",
    "classify_section",
    "infer_document_type",
    "normalize_document_type",
]
