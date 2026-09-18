"""Document Domain Value Objects.

Value Objects encapsulate domain concepts that are defined by their value
rather than identity.  They provide self-validating constructors so that
invalid data can never enter the domain model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.domain import ValueObject


@dataclass(frozen=True)
class ContentHash(ValueObject):
    """SHA-256 hex digest identifying document content."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not re.fullmatch(r"[0-9a-f]{64}", self.value):
            raise ValueError(
                f"ContentHash must be a 64-character lowercase hex string, got: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StorageUri(ValueObject):
    """URI pointing to a stored document blob."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("StorageUri must be a non-empty string.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MimeType(ValueObject):
    """Internet media type (e.g. ``application/pdf``)."""

    value: str

    _PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9!#$&\-.^_+]*\/[a-zA-Z0-9][a-zA-Z0-9!#$&\-.^_+]*$")

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self._PATTERN.match(self.value):
            raise ValueError(f"Invalid MIME type: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Filename(ValueObject):
    """A validated document filename."""

    value: str

    MAX_LENGTH = 500

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("Filename must be a non-empty string.")
        if len(self.value) > self.MAX_LENGTH:
            raise ValueError(f"Filename exceeds maximum length of {self.MAX_LENGTH} characters.")

    def __str__(self) -> str:
        return self.value


__all__ = ["ContentHash", "StorageUri", "MimeType", "Filename"]
