"""RAG Core — embedding, indexing, retrieval, and generation."""

from .engine import RAGEngine
from .ocr import GeminiOCR, OCRProvider

__all__ = ["GeminiOCR", "OCRProvider", "RAGEngine"]
