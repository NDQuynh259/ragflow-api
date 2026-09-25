"""File validation, security sanitization, and MIME magic-bytes sniffing."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import (
    EmptyFileException,
    FileTooLargeException,
    InvalidFileContentException,
    InvalidFileTypeException,
)

DEFAULT_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

DEFAULT_ALLOWED_EXTENSIONS: set[str] = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".csv",
    ".xlsx",
    ".pptx",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
}

BLOCKED_EXECUTABLE_EXTENSIONS: set[str] = {
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".vbs",
    ".js",
    ".dll",
    ".so",
    ".bin",
    ".msi",
    ".php",
    ".jar",
    ".py",
}

EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class ValidatedFile:
    """Carries validated and sanitized file metadata and content."""

    filename: str
    extension: str
    content: bytes
    file_size: int
    content_hash: str
    detected_mime_type: str


class FileValidator:
    """Enforces file size, path traversal sanitization, and binary magic-bytes security."""

    def __init__(
        self,
        max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        allowed_extensions: set[str] | None = None,
        strict_magic_bytes: bool = False,
    ) -> None:
        self.max_size_bytes = max_size_bytes
        self.allowed_extensions = set(
            ext.lower() for ext in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)
        )
        self.strict_magic_bytes = strict_magic_bytes

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent Path Traversal attacks and invalid characters."""
        # 1. Extract purely the base name (strip directory components)
        clean = os.path.basename(filename.strip().replace("\\", "/"))

        # 2. Strip leading dots to prevent hidden files or traversal tricks like ..
        clean = clean.lstrip(".")

        # 3. Filter characters: keep alphanumeric, unicode letters, dashes, underscores, and dots
        clean = re.sub(r"[^\w\.\-\s]", "_", clean)
        clean = re.sub(r"_+", "_", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        if not clean or clean.count(".") == 0:
            return clean or "unnamed_document.bin"

        return clean

    @staticmethod
    def calculate_hash(content: bytes) -> str:
        """Calculate SHA-256 hexadecimal hash of file content."""
        return hashlib.sha256(content).hexdigest()

    def validate(
        self,
        filename: str,
        content: bytes,
        declared_mime_type: str | None = None,
    ) -> ValidatedFile:
        """Execute full validation suite: size, filename, extension, magic bytes, and hashing."""
        safe_name = self.sanitize_filename(filename)

        # 1. Empty content check
        file_size = len(content)
        if file_size == 0:
            raise EmptyFileException(filename=safe_name)

        # 2. Maximum size check
        if file_size > self.max_size_bytes:
            raise FileTooLargeException(size=file_size, max_size=self.max_size_bytes)

        # 3. Extension validation
        ext = Path(safe_name).suffix.lower()
        if not ext or ext in BLOCKED_EXECUTABLE_EXTENSIONS or ext not in self.allowed_extensions:
            raise InvalidFileTypeException(
                filename=safe_name,
                mime_type=declared_mime_type,
                allowed=sorted(list(self.allowed_extensions)),
            )

        # 4. Binary Magic Bytes Sniffing & Anti-Spoofing Security Gate
        detected_mime = self._sniff_and_verify_content(safe_name, ext, content)

        # 5. Content Hashing
        content_hash = self.calculate_hash(content)

        return ValidatedFile(
            filename=safe_name,
            extension=ext,
            content=content,
            file_size=file_size,
            content_hash=content_hash,
            detected_mime_type=detected_mime
            or declared_mime_type
            or EXTENSION_MIME_MAP.get(ext, "application/octet-stream"),
        )

    def _sniff_and_verify_content(self, filename: str, ext: str, content: bytes) -> str:
        """Verify binary headers (magic numbers) to ensure file content matches declared extension."""
        # A. Block dangerous executable signatures disguised as document
        if content.startswith(b"MZ"):  # Windows PE executable
            raise InvalidFileContentException(
                filename=filename,
                expected_type=ext,
                reason="File content contains Windows PE executable signature.",
            )
        if content.startswith(b"\x7fELF"):  # Linux ELF executable
            raise InvalidFileContentException(
                filename=filename,
                expected_type=ext,
                reason="File content contains Linux ELF executable signature.",
            )
        if content.startswith(b"\xca\xfe\xba\xbe"):  # Java bytecode
            raise InvalidFileContentException(
                filename=filename,
                expected_type=ext,
                reason="File content contains Java bytecode signature.",
            )

        # B. Check specific formats
        if ext == ".pdf":
            if content.startswith(b"%PDF-"):
                return "application/pdf"
            if self.strict_magic_bytes:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type="PDF",
                    reason="Missing '%PDF-' header signature.",
                )
            return "application/pdf"

        if ext in (".docx", ".xlsx", ".pptx"):
            # Office OpenXML files are ZIP archives
            if content.startswith(b"PK\x03\x04") or content.startswith(b"PK\x05\x06"):
                return EXTENSION_MIME_MAP[ext]
            if self.strict_magic_bytes:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type=f"Office XML ({ext})",
                    reason="Missing ZIP container header signature.",
                )
            return EXTENSION_MIME_MAP[ext]

        if ext == ".doc":
            # OLE2 Compound Document
            if content.startswith(b"\xd0\xcf\x11\xe0"):
                return "application/msword"
            if self.strict_magic_bytes:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type="Word DOC",
                    reason="Missing OLE2 Compound Document header signature.",
                )
            return "application/msword"

        if ext == ".png":
            if content.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if self.strict_magic_bytes:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type="PNG Image",
                    reason="Missing PNG header signature.",
                )
            return "image/png"

        if ext in (".jpg", ".jpeg"):
            if content.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if self.strict_magic_bytes:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type="JPEG Image",
                    reason="Missing JPEG header signature.",
                )
            return "image/jpeg"

        if ext in (".txt", ".md", ".csv", ".json"):
            # Text based formats: check null bytes (often binary payload)
            header_sample = content[:4096]
            if b"\x00" in header_sample:
                raise InvalidFileContentException(
                    filename=filename,
                    expected_type=f"Text/Data ({ext})",
                    reason="Binary null bytes detected in plain text file.",
                )
            return EXTENSION_MIME_MAP[ext]

        return EXTENSION_MIME_MAP.get(ext, "application/octet-stream")


__all__ = [
    "DEFAULT_ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "EXTENSION_MIME_MAP",
    "FileValidator",
    "ValidatedFile",
]
