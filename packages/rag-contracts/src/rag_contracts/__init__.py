"""Shared contracts between rag-document-pipeline and rag-core."""

from .chunks import ChunkRecord, SearchResult

__all__ = ["ChunkRecord", "SearchResult"]
