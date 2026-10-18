"""Mô-đun kiểm định tính toàn vẹn của chunk (Validation & Integrity Reporting).

Cung cấp các công cụ kiểm tra độ dài token, loại bỏ trùng lặp, phát hiện chunk rỗng
và lập báo cáo chẩn đoán độ bao phủ phần tử bố cục của tài liệu.
"""

from .chunk_validator import ChunkValidator
from .integrity_report import IntegrityReport

__all__ = ["ChunkValidator", "IntegrityReport"]
