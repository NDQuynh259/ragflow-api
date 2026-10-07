"""RAG Core — embedding, indexing, retrieval, and generation."""

from .engine import RAGEngine
from .ports.ocr import OCRProvider
from .providers.ocr import GeminiOCR

__all__ = ["GeminiOCR", "OCRProvider", "RAGEngine"]
