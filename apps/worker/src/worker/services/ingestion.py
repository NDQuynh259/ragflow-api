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
    layout_uri: str | None = None


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
        """Fetch bytes from storage, process chunks through pipeline, persist layout to storage, and index in RAGEngine."""
        import gc
        import json

        file_bytes = self.storage.get(storage_uri)
        file_size = len(file_bytes)
        logger.info("Read %d bytes from storage URI: %s", file_size, storage_uri)

        processed = self.pipeline.process(
            file_bytes,
            filename=filename,
            document_id=str(document_id),
        )
        # 1. Release raw file bytes immediately from RAM
        del file_bytes
        gc.collect()

        logger.info(
            "Processed document %s: %d pages, %d chunks",
            document_id,
            processed.page_count,
            len(processed.chunks),
        )

        layout_uri: str | None = None
        # 2. Persist parsed layout JSON to Storage (Enterprise pattern: no RAM bloat, reusable for re-chunking)
        if hasattr(processed, "elements") and processed.elements:
            try:
                elements_dump = [
                    el.model_dump() if hasattr(el, "model_dump") else el.__dict__
                    for el in processed.elements
                ]
                layout_json = json.dumps(elements_dump, ensure_ascii=False)
                layout_uri = self.storage.save(
                    filename=f"{document_id}_layout.json",
                    content=layout_json.encode("utf-8"),
                    workspace_id=workspace_id,
                )
                logger.info("Persisted parsed layout to storage URI: %s", layout_uri)

                # Immediately clear elements from RAM
                if isinstance(processed.elements, list):
                    processed.elements.clear()
                del elements_dump, layout_json
                gc.collect()
            except Exception as exc:
                logger.warning("Could not persist parsed layout JSON: %s", exc)

        for chunk in processed.chunks:
            chunk.workspace_id = str(workspace_id)

        # 3. Index chunks into vector store in batches
        indexed_count = self.engine.index(processed.chunks)
        logger.info(
            "Successfully indexed %d chunks for document %s",
            indexed_count,
            document_id,
        )

        page_count = processed.page_count
        chunk_count = len(processed.chunks)

        # 4. Clean up processed container from RAM
        del processed
        gc.collect()

        return IngestionPipelineResult(
            page_count=page_count,
            chunk_count=chunk_count,
            file_size=file_size,
            indexed_count=indexed_count,
            layout_uri=layout_uri,
        )


__all__ = [
    "DocumentIngestionService",
    "IngestionPipelineResult",
]
