"""Facade của package chunking: Public surface cho toàn bộ hệ thống băm nhỏ tài liệu.

Module này cung cấp các điểm truy cập chính (Public API) cho ứng dụng bên ngoài và pipeline:
- `AdaptiveChunkingRouter`: Bộ điều phối băm nhỏ thích ứng theo loại tài liệu và section.
- `MultimodalChunker`: Bộ điều phối băm nhỏ toàn diện theo thứ tự đọc (kế thừa AdaptiveChunkingRouter).
- `TextChunker`: Chiến lược băm văn bản dựa trên phân đoạn ngữ nghĩa (Topic Shifts).
- `TableChunker`: Chiến lược băm bảng biểu bảo toàn cấu trúc Markdown Table.
- `ImageChunker`: Chiến lược băm hình ảnh kết hợp Triage kích thước và Vision AI (VLM).
- `Chunker`: Giao diện (Protocol) chuẩn cho mọi bộ băm tài liệu.
- `classify_document`, `classify_section`: Bộ phân loại tài liệu 3 tầng và phân đoạn section.
"""

from .business_plan import BusinessPlanPolicy
from .classifier import (
    DOCUMENT_TYPE_ALIASES,
    DOCUMENT_TYPE_PATTERNS,
    DocumentType,
    classify_document,
    classify_section,
    infer_document_type,
    normalize_document_type,
)
from .core import Chunker
from .legal import LegalPolicy
from .multimodal import MultimodalChunker
from .procedure import ProcedurePolicy
from .report import ReportPolicy
from .router import (
    CHUNKING_PROFILES,
    AdaptiveChunkingRouter,
    ChunkingProfile,
    enrich_chunk_metadata,
    extract_domain_metadata,
)
from .semantic import SemanticPolicy
from .strategies import (
    ImageChunker,
    LegalHierarchyChunker,
    LegalHierarchyConfig,
    TableChunker,
    TextChunker,
)
from .text import StructureAwareTextPolicy
from .wiki import WikiPolicy

__all__ = [
    "BusinessPlanPolicy",
    "LegalPolicy",
    "ProcedurePolicy",
    "ReportPolicy",
    "SemanticPolicy",
    "StructureAwareTextPolicy",
    "WikiPolicy",
    "AdaptiveChunkingRouter",
    "CHUNKING_PROFILES",
    "Chunker",
    "ChunkingProfile",
    "DOCUMENT_TYPE_ALIASES",
    "DOCUMENT_TYPE_PATTERNS",
    "DocumentType",
    "ImageChunker",
    "LegalHierarchyChunker",
    "LegalHierarchyConfig",
    "MultimodalChunker",
    "TableChunker",
    "TextChunker",
    "classify_document",
    "classify_section",
    "enrich_chunk_metadata",
    "extract_domain_metadata",
    "infer_document_type",
    "normalize_document_type",
]
