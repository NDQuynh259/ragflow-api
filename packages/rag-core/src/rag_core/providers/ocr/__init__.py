"""OCR provider implementations."""

from .gemini import GeminiOCR
from .router import DualOCRRouter
from .tesseract import TesseractOCR
from .vision import (
    DEFAULT_VISION_PROMPT,
    VISION_ANALYSIS_PROMPT,
    GeminiVisionAnalyzer,
    ImageAnalysisResult,
)

__all__ = [
    "DEFAULT_VISION_PROMPT",
    "DualOCRRouter",
    "GeminiOCR",
    "GeminiVisionAnalyzer",
    "ImageAnalysisResult",
    "TesseractOCR",
    "VISION_ANALYSIS_PROMPT",
]
