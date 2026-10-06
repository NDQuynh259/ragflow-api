"""Worker Document Ingestion Service for pipeline execution."""

from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
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

    def _upload_images(
        self,
        image_dir: Path,
        *,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> dict[str, str]:
        """Upload extracted images and return local filename-to-URI mappings."""
        image_uris: dict[str, str] = {}
        for image_path in image_dir.rglob("*"):
            if not image_path.is_file():
                continue
            try:
                uri = self.storage.save(
                    filename=image_path.name,
                    content=image_path.read_bytes(),
                    object_path=(
                        f"workspaces/{workspace_id}/{document_id}/images/{image_path.name}"
                    ),
                )
                image_uris[image_path.name] = uri
                logger.info("Uploaded extracted image %s to %s", image_path.name, uri)
            except Exception:
                logger.exception("Could not upload extracted image %s", image_path)
        return image_uris

    @staticmethod
    def _rewrite_image_uris(elements: list, image_uris: dict[str, str]) -> None:
        """Replace parser-local image paths with durable object-storage URIs."""
        for element in elements:
            image_data = getattr(element, "image_data", None)
            if image_data and image_data.uri:
                image_name = Path(image_data.uri).name
                if image_name in image_uris:
                    image_data.uri = image_uris[image_name]
            if getattr(element, "source", None):
                source_name = Path(element.source).name
                if source_name in image_uris:
                    element.source = image_uris[source_name]
            for key in ("image_path", "uri"):
                value = element.metadata.get(key)
                if value:
                    image_name = Path(str(value)).name
                    if image_name in image_uris:
                        element.metadata[key] = image_uris[image_name]

    @staticmethod
    def _rewrite_chunk_image_uris(chunks: list, image_uris: dict[str, str]) -> None:
        """Replace parser-local image paths in chunk metadata with durable URIs."""
        for chunk in chunks:
            for key in ("image_path", "image_uri", "source"):
                value = getattr(chunk.metadata, key, None) or chunk.metadata.get(key)
                if value:
                    image_name = Path(str(value)).name
                    if image_name in image_uris:
                        if hasattr(chunk.metadata, key):
                            setattr(chunk.metadata, key, image_uris[image_name])
                        else:
                            chunk.metadata[key] = image_uris[image_name]

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

        # Extract images to a temp directory so they can be uploaded to object storage
        image_dir: Path | None = None
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            temp_dir = tempfile.TemporaryDirectory(prefix="rag-ingest-images-")
            image_dir = Path(temp_dir.name)
            processed = self.pipeline.process(
                file_bytes,
                filename=filename,
                document_id=str(document_id),
                image_dir=image_dir,
            )
        except TypeError:
            # Parser does not accept image_dir
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

        # 2. Upload extracted images to object storage under the document prefix
        image_uris: dict[str, str] = {}
        if image_dir and image_dir.is_dir():
            image_uris = self._upload_images(
                image_dir,
                document_id=document_id,
                workspace_id=workspace_id,
            )
        # Release temp image directory before rewriting URIs
        if temp_dir is not None:
            temp_dir.cleanup()
            temp_dir = None
            image_dir = None
        if image_uris:
            self._rewrite_image_uris(processed.elements, image_uris)
            self._rewrite_chunk_image_uris(processed.chunks, image_uris)

        layout_uri: str | None = None
        # 3. Persist parsed layout JSON to Storage (Enterprise pattern: no RAM bloat, reusable for re-chunking)
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
                    object_path=f"workspaces/{workspace_id}/{document_id}/{document_id}_layout.json",
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

        # 4. Index chunks into vector store in batches
        indexed_count = self.engine.index(processed.chunks)
        logger.info(
            "Successfully indexed %d chunks for document %s",
            indexed_count,
            document_id,
        )

        page_count = processed.page_count
        chunk_count = len(processed.chunks)

        # 5. Clean up processed container from RAM
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
