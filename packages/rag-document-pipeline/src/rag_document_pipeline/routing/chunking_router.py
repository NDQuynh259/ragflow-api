"""Bộ định tuyến phân đoạn thích ứng (Adaptive Chunk Router API).

Tái xuất (re-export) bộ định tuyến phân đoạn `AdaptiveChunkingRouter`, hồ sơ cấu hình băm `ChunkingProfile`,
bảng cấu hình mặc định `CHUNKING_PROFILES` và các hàm làm giàu siêu dữ liệu nghiệp vụ từ module chunking.
"""

from rag_document_pipeline.chunking.router import (
    CHUNKING_PROFILES,
    AdaptiveChunkingRouter,
    ChunkingProfile,
    enrich_chunk_metadata,
    extract_domain_metadata,
)

__all__ = [
    "CHUNKING_PROFILES",
    "AdaptiveChunkingRouter",
    "ChunkingProfile",
    "enrich_chunk_metadata",
    "extract_domain_metadata",
]
