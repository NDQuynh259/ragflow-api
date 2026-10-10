"""Optional local Tesseract OCR provider."""

from __future__ import annotations

import ipaddress
import logging
import mimetypes
import os
import socket
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class TesseractOCR:
    """Extract text with Tesseract from local paths or safe HTTP(S) URLs."""

    def __init__(
        self,
        *,
        lang: str = "eng+vie",
        timeout: float = 30.0,
        max_image_bytes: int | None = None,
        allow_private_network: bool = False,
    ) -> None:
        self.lang = lang
        self.timeout = timeout
        self.max_image_bytes = max_image_bytes or int(
            os.environ.get("OCR_MAX_IMAGE_BYTES", "10485760")
        )
        self.allow_private_network = allow_private_network or (
            os.environ.get("OCR_ALLOW_PRIVATE_NETWORK", "").lower() in {"1", "true", "yes"}
        )
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self.max_image_bytes <= 0:
            raise ValueError("max_image_bytes must be greater than zero")

    def __call__(self, image_source: str) -> str:
        """Return stripped OCR text, raising provider errors to the router."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Tesseract OCR dependencies are not installed") from exc

        parsed = urlparse(image_source)
        temporary_path: str | None = None
        try:
            if parsed.scheme in {"http", "https"}:
                data, suffix = self._download_image(image_source, parsed.hostname)
                with NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
                    temporary.write(data)
                    temporary_path = temporary.name
                path = temporary_path
            elif parsed.scheme:
                raise ValueError("Image source must be a local path or HTTP(S) URL")
            else:
                path = image_source
                if Path(path).stat().st_size > self.max_image_bytes:
                    raise ValueError("Image exceeds OCR_MAX_IMAGE_BYTES limit")

            with Image.open(path) as image:
                return (pytesseract.image_to_string(image, lang=self.lang) or "").strip()
        except Exception:
            logger.warning("Tesseract OCR failed for %s", image_source, exc_info=True)
            raise
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove temporary OCR image %s", temporary_path)

    def _download_image(self, image_source: str, hostname: str | None) -> tuple[bytes, str]:
        self._assert_url_allowed(hostname)
        request = Request(image_source, headers={"User-Agent": "ragflow-ocr/1.0"})
        with urlopen(request, timeout=self.timeout) as response:
            data = response.read(self.max_image_bytes + 1)
            if len(data) > self.max_image_bytes:
                raise ValueError("Image exceeds OCR_MAX_IMAGE_BYTES limit")
            content_type = response.headers.get_content_type()
        extension = mimetypes.guess_extension(content_type) or ".img"
        return data, extension

    def _assert_url_allowed(self, hostname: str | None) -> None:
        if self.allow_private_network:
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


__all__ = ["TesseractOCR"]
