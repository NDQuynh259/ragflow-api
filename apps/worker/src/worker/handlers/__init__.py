"""Worker action handlers."""

from __future__ import annotations

from worker.handlers.index_document import IndexDocumentCommand, IndexDocumentHandler

__all__ = [
    "IndexDocumentCommand",
    "IndexDocumentHandler",
]
