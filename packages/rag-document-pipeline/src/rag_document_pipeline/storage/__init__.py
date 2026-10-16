"""Storage adapters for the document pipeline."""

from rag_document_pipeline.storage.local import LocalFileStorage, LocalStorageAdapter
from rag_document_pipeline.storage.ports import ObjectStoragePort

__all__ = ["LocalFileStorage", "LocalStorageAdapter", "ObjectStoragePort"]
