"""Bộ xử lý phần tử hình ảnh (Figure Processor).

Tái xuất `ImageChunker` dưới dạng bí danh `FigureProcessor` nhằm duy trì hành vi lọc ảnh thông minh
(image triage: loại ảnh nhỏ, icon, đường viền) và trích xuất ngữ cảnh hình ảnh.
"""

from rag_document_pipeline.chunking.strategies.image import ImageChunker

FigureProcessor = ImageChunker

__all__ = ["FigureProcessor", "ImageChunker"]
