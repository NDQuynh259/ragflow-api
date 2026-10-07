"""Gemini-backed OCR callback."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


class GeminiOCR:
    """Extract text from local image files or HTTP(S) image URLs with Gemini."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_OCR_MODEL", "gemini-2.0-flash")
        self._timeout = timeout
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is required for OCR.")

        from google import genai

        self._client = genai.Client(api_key=self._api_key)

    def __call__(self, image_source: str) -> str:
        """Return text in reading order, or an empty string when no text exists."""
        image_bytes, mime_type = self._read_image(image_source)
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_text(
                    text=(
                        "Transcribe every visible character in this image exactly. "
                        "Preserve the original language, numbers, punctuation, and line order. "
                        "Return only the transcription. If there is no readable text, return an empty string."
                    )
                ),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=4096,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )
        return (response.text or "").strip()

    def _read_image(self, image_source: str) -> tuple[bytes, str]:
        parsed = urlparse(image_source)
        if parsed.scheme in {"http", "https"}:
            with urlopen(image_source, timeout=self._timeout) as response:
                data = response.read()
                content_type = response.headers.get_content_type()
            return data, content_type if content_type.startswith("image/") else "image/jpeg"

        path = Path(image_source)
        data = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(path.name)
        return data, mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"


__all__ = ["GeminiOCR"]
