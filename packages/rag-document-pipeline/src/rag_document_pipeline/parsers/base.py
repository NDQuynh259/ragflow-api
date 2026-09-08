from __future__ import annotations

from typing import Protocol
from rag_document_pipeline.models import LayoutElement

class ParserError(RuntimeError):
    """Raised when a document parser cannot produce layout elements."""

class Parser(Protocol):
    def parse(self, content: bytes, *, filename: str) -> list[LayoutElement]: ...
