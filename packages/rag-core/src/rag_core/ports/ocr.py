"""OCR provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OCRProvider(Protocol):
    """Protocol for providers that extract text from an image source."""

    def __call__(self, image_source: str) -> str:
        """Extract and return text from a local path or remote image URI."""
        ...


__all__ = ["OCRProvider"]
