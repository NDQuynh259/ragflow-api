"""Bộ phân loại tài liệu và phân đoạn (Document & Section Classifier API).

Tái xuất (re-export) enum 5 loại tài liệu chuẩn `DocumentType`, các hàm phân loại 3 tầng
`classify_document`, `classify_section`, hàm chuẩn hóa `normalize_document_type`,
và các mẫu quy tắc nhận diện (regex & alias).
"""

from rag_document_pipeline.chunking.classifier import (
    DOCUMENT_TYPE_ALIASES,
    DOCUMENT_TYPE_PATTERNS,
    DocumentType,
    classify_document,
    classify_section,
    infer_document_type,
    normalize_document_type,
)

__all__ = [
    "DOCUMENT_TYPE_ALIASES",
    "DOCUMENT_TYPE_PATTERNS",
    "DocumentType",
    "classify_document",
    "classify_section",
    "infer_document_type",
    "normalize_document_type",
]
