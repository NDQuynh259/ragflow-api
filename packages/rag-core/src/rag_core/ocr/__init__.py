"""OCR providers used by the RAG application."""

from .base import OCRProvider
from .gemini import GeminiOCR

__all__ = ["GeminiOCR", "OCRProvider"]
