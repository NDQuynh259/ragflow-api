"""Fallback routing for local and vision OCR providers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DualOCRRouter:
    """Try a fast OCR provider before falling back to a VLM OCR provider."""

    def __init__(
        self,
        fast_ocr: Any = None,
        vlm_ocr: Any = None,
        *,
        min_text_length: int = 20,
    ) -> None:
        if min_text_length < 0:
            raise ValueError("min_text_length must be non-negative")
        self.fast_ocr = fast_ocr
        self.vlm_ocr = vlm_ocr
        self.min_text_length = min_text_length

    def __call__(self, image_source: str) -> str:
        """Return fast OCR output when viable, otherwise use the VLM fallback."""
        if self.fast_ocr is not None:
            try:
                fast_text = self.fast_ocr(image_source)
                if isinstance(fast_text, str) and len(fast_text.strip()) > self.min_text_length:
                    return fast_text.strip()
                logger.warning("Fast OCR returned low-quality text for %s", image_source)
            except Exception as exc:
                logger.warning("Fast OCR failed for %s: %s", image_source, exc)

        if self.vlm_ocr is not None:
            try:
                vlm_text = self.vlm_ocr(image_source)
                return vlm_text.strip() if isinstance(vlm_text, str) else ""
            except Exception as exc:
                logger.warning("VLM OCR fallback failed for %s: %s", image_source, exc)

        logger.warning("No OCR provider available for %s", image_source)
        return ""


__all__ = ["DualOCRRouter"]
