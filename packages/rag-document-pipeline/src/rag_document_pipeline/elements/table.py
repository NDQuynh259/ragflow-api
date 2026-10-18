"""Bộ xử lý phần tử bảng biểu (Table Processor).

Tái xuất `TableChunker` dưới dạng bí danh `TableProcessor` nhằm bảo toàn cấu trúc bảng biểu
(tiêu đề cột, các hàng dữ liệu, chú thích caption/footnote) khi phân đoạn tài liệu.
"""

from rag_document_pipeline.chunking.strategies.table import TableChunker

TableProcessor = TableChunker

__all__ = ["TableChunker", "TableProcessor"]
