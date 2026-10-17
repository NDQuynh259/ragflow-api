"""Always-on multimodal reading-order chunk router with adaptive classification.

Module này điều phối luồng băm nhỏ tài liệu đa phương thức (Multimodal Reading-Order Routing)
thích ứng theo 5 loại tài liệu và từng phân đoạn (Section):
1. Nhận danh sách các `LayoutElement` đã qua chuẩn hóa và bóc tách bố cục.
2. Tự động nhận diện loại tài liệu (Tier 1 -> Tier 2 -> Tier 3) và loại từng Section.
3. Điều phối định tuyến thích ứng (AdaptiveChunkingRouter) theo thứ tự đọc:
   - Text chunks: Băm theo ranh giới ngữ nghĩa hoặc cấu trúc điều khoản tùy theo loại tài liệu/section.
   - Table chunks: Giữ nguyên `kind="table"`, kết cấu Markdown lặp tiêu đề cột.
   - Image chunks: Giữ nguyên `kind="figure"`, qua bộ lọc Triage và mô hình Vision VLM.
4. Trích xuất và bổ sung metadata ngữ cảnh chuyên biệt (step_number, article_id, report_period, scenario...).
5. Thiết lập liên kết chéo hai chiều (`related_chunk_ids`) cho các bảng biểu và hình ảnh được nhắc tới.
6. Đánh số chỉ mục `index` tuần tự theo đúng thứ tự đọc của tài liệu gốc.
"""

from __future__ import annotations

from .router import (
    CHUNKING_PROFILES,
    AdaptiveChunkingRouter,
    ChunkingProfile,
    enrich_chunk_metadata,
    extract_domain_metadata,
)


class MultimodalChunker(AdaptiveChunkingRouter):
    """Route text, tables and images to modality-specific chunkers in reading order with adaptive routing."""

    pass


__all__ = [
    "CHUNKING_PROFILES",
    "AdaptiveChunkingRouter",
    "ChunkingProfile",
    "MultimodalChunker",
    "enrich_chunk_metadata",
    "extract_domain_metadata",
]
