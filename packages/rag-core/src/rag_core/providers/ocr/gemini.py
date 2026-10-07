"""Gemini-backed OCR callback."""

from __future__ import annotations

import ipaddress
import mimetypes
import os
import socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class GeminiOCR:
    """Extract text from local image files or HTTP(S) image URLs with Gemini."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        max_image_bytes: int | None = None,
        allow_private_network: bool = False,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_OCR_MODEL", "gemini-2.0-flash")
        self._timeout = timeout
        self._max_image_bytes = max_image_bytes or int(
            os.environ.get("OCR_MAX_IMAGE_BYTES", "10485760")
        )
        self._allow_private_network = allow_private_network or (
            os.environ.get("OCR_ALLOW_PRIVATE_NETWORK", "").lower() in {"1", "true", "yes"}
        )
        if self._timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self._max_image_bytes <= 0:
            raise ValueError("max_image_bytes must be greater than zero")
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
            self._assert_url_allowed(parsed.hostname)
            request = Request(image_source, headers={"User-Agent": "ragflow-ocr/1.0"})
            with urlopen(request, timeout=self._timeout) as response:
                data = response.read(self._max_image_bytes + 1)
                if len(data) > self._max_image_bytes:
                    raise ValueError("Image exceeds OCR_MAX_IMAGE_BYTES limit")
                content_type = response.headers.get_content_type()
            return data, content_type if content_type.startswith("image/") else "image/jpeg"

        path = Path(image_source)
        size = path.stat().st_size
        if size > self._max_image_bytes:
            raise ValueError("Image exceeds OCR_MAX_IMAGE_BYTES limit")
        data = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(path.name)
        return data, mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"

    def _assert_url_allowed(self, hostname: str | None) -> None:
        """Reject URLs resolving to private, loopback, or link-local addresses."""
        if self._allow_private_network:
            return
        if not hostname:
            raise ValueError("Image URL must include a hostname")
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
        except socket.gaierror as exc:
            raise ValueError("Image URL hostname could not be resolved") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Image URL resolves to a disallowed network address")


__all__ = ["GeminiOCR"]
