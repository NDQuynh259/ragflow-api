"""Unit tests for FileValidator and security checks."""

from __future__ import annotations

import pytest

from core.exceptions import (
    EmptyFileException,
    FileTooLargeException,
    InvalidFileContentException,
    InvalidFileTypeException,
)
from core.storage import FileValidator


def test_sanitize_filename() -> None:
    # 1. Path traversal attacks
    assert FileValidator.sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert FileValidator.sanitize_filename("..\\..\\windows\\system32\\cmd.pdf") == "cmd.pdf"
    assert FileValidator.sanitize_filename("folder/subfolder/file.pdf") == "file.pdf"

    # 2. Leading dots
    assert FileValidator.sanitize_filename("...hidden.pdf") == "hidden.pdf"

    # 3. Special characters & spaces
    assert FileValidator.sanitize_filename("my  file @#$! 2026.docx") == "my file _ 2026.docx"


def test_validate_empty_file() -> None:
    validator = FileValidator()
    with pytest.raises(EmptyFileException):
        validator.validate("test.pdf", b"")


def test_validate_oversized_file() -> None:
    validator = FileValidator(max_size_bytes=100)
    with pytest.raises(FileTooLargeException):
        validator.validate("test.pdf", b"%PDF-" + b"0" * 150)


def test_validate_disallowed_extension() -> None:
    validator = FileValidator()
    # Executables explicitly blocked
    with pytest.raises(InvalidFileTypeException):
        validator.validate("script.sh", b"echo hello")

    with pytest.raises(InvalidFileTypeException):
        validator.validate("payload.exe", b"MZdummy")

    with pytest.raises(InvalidFileTypeException):
        validator.validate("no_extension", b"some content")


def test_validate_blocks_malicious_executables_disguised_as_pdf() -> None:
    validator = FileValidator()

    # Windows executable renamed to .pdf
    with pytest.raises(InvalidFileContentException, match="Windows PE"):
        validator.validate("malware.pdf", b"MZ\x90\x00\x03\x00\x00\x00")

    # Linux ELF executable renamed to .pdf
    with pytest.raises(InvalidFileContentException, match="Linux ELF"):
        validator.validate("exploit.pdf", b"\x7fELF\x02\x01\x01\x00")

    # Java bytecode renamed to .pdf
    with pytest.raises(InvalidFileContentException, match="Java bytecode"):
        validator.validate("applet.pdf", b"\xca\xfe\xba\xbe\x00\x00\x00")


def test_validate_text_with_null_bytes() -> None:
    validator = FileValidator()
    # Text file containing hidden binary payload (null byte)
    with pytest.raises(InvalidFileContentException, match="Binary null bytes detected"):
        validator.validate("notes.txt", b"Normal text\x00Malicious payload")


def test_validate_strict_magic_bytes() -> None:
    strict_validator = FileValidator(strict_magic_bytes=True)

    # Valid PDF
    validated_pdf = strict_validator.validate("doc.pdf", b"%PDF-1.7 actual content")
    assert validated_pdf.detected_mime_type == "application/pdf"

    # Invalid PDF content under strict mode
    with pytest.raises(InvalidFileContentException, match="Missing '%PDF-' header"):
        strict_validator.validate("fake.pdf", b"Just plain text pretending to be PDF")

    # Valid DOCX / ZIP
    validated_docx = strict_validator.validate("doc.docx", b"PK\x03\x04\x14\x00\x06\x00")
    assert "openxmlformats" in validated_docx.detected_mime_type

    # Invalid DOCX content under strict mode
    with pytest.raises(InvalidFileContentException, match="Missing ZIP container"):
        strict_validator.validate("fake.docx", b"Not a real docx archive")


def test_content_hashing() -> None:
    validator = FileValidator()
    content = b"%PDF-1.4 consistent content for hash test"
    v1 = validator.validate("file1.pdf", content)
    v2 = validator.validate("file2.pdf", content)

    assert v1.content_hash == v2.content_hash
    assert len(v1.content_hash) == 64  # SHA-256 hex string length
