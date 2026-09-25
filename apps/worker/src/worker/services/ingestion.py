"""Worker Document Ingestion Service for pipeline execution."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import ObjectStoragePort
    from rag_core.engine import RAGEngine
    from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionPipelineResult:
    """Carries the outcome of document parsing, chunking, and indexing."""

    page_count: int
    chunk_count: int
    file_size: int
    indexed_count: int


class DocumentIngestionService:
    """Service that orchestrates file retrieval, parsing, chunking, and vector indexing."""

    def __init__(
        self,
        storage: ObjectStoragePort,
        pipeline: DocumentPipeline,
        engine: RAGEngine,
    ) -> None:
        self.storage = storage
        self.pipeline = pipeline
        self.engine = engine

    def execute_pipeline(
        self,
        storage_uri: str,
        filename: str,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> IngestionPipelineResult:
        """Fetch bytes from storage, process chunks through pipeline, and index in RAGEngine."""
        file_bytes = self.storage.get(storage_uri)
        logger.info("Read %d bytes from storage URI: %s", len(file_bytes), storage_uri)

        processed = self.pipeline.process(
            file_bytes,
            filename=filename,
            document_id=str(document_id),
        )
        logger.info(
            "Processed document %s: %d pages, %d chunks",
            document_id,
            processed.page_count,
            len(processed.chunks),
        )

        for chunk in processed.chunks:
            chunk.workspace_id = str(workspace_id)

        indexed_count = self.engine.index(processed.chunks)
        logger.info(
            "Successfully indexed %d chunks for document %s",
            indexed_count,
            document_id,
        )

        return IngestionPipelineResult(
            page_count=processed.page_count,
            chunk_count=len(processed.chunks),
            file_size=len(file_bytes),
            indexed_count=indexed_count,
        )


__all__ = [
    "DocumentIngestionService",
    "IngestionPipelineResult",
]
