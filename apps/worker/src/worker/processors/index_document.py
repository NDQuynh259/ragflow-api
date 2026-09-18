"""Document indexing job processor."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import text

from core.database.session import SessionLocal
from core.storage.local import LocalStorageAdapter
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


def process_index_document(
    job_id: str,
    document_id: str,
    storage_uri: str,
    workspace_id: str,
) -> int:
    """Execute document ingestion pipeline: parse -> chunk -> embed -> index."""
    logger.info(
        "Starting ingestion job %s for document %s (workspace: %s)",
        job_id,
        document_id,
        workspace_id,
    )
    start_time = time.monotonic()
    now_utc = datetime.now(UTC)

    # 1. Update job to 'running' and document to 'processing'
    with SessionLocal() as session:
        session.execute(
            text(
                "UPDATE ingestion_jobs SET status = 'running', started_at = :now WHERE id = :job_id"
            ),
            {"now": now_utc, "job_id": job_id},
        )
        session.execute(
            text("UPDATE documents SET status = 'processing' WHERE id = :doc_id"),
            {"doc_id": document_id},
        )
        # Fetch document filename if available
        row = session.execute(
            text("SELECT filename FROM documents WHERE id = :doc_id"),
            {"doc_id": document_id},
        ).fetchone()
        filename = row[0] if row else "document.pdf"
        session.commit()

    try:
        # 2. Read raw file bytes from storage
        storage = LocalStorageAdapter()
        file_bytes = storage.get(storage_uri)
        logger.info("Read %d bytes from storage URI: %s", len(file_bytes), storage_uri)

        # 3. Parse & chunk document
        pipeline = DocumentPipeline()
        processed = pipeline.process(file_bytes, filename=filename, document_id=document_id)
        logger.info(
            "Processed document %s: %d pages, %d chunks",
            document_id,
            processed.page_count,
            len(processed.chunks),
        )

        # 4. Attach workspace_id to each chunk
        for chunk in processed.chunks:
            chunk.workspace_id = workspace_id

        # 5. Embed and index chunks into vector store
        engine = RAGEngine.from_env()
        indexed_count = engine.index(processed.chunks)
        logger.info("Successfully indexed %d chunks for document %s", indexed_count, document_id)

        # 6. Mark job as 'completed' and document as 'ready'
        elapsed = time.monotonic() - start_time
        completed_at = datetime.now(UTC)
        with SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE ingestion_jobs "
                    "SET status = 'completed', completed_at = :now, elapsed_seconds = :elapsed "
                    "WHERE id = :job_id"
                ),
                {"now": completed_at, "elapsed": elapsed, "job_id": job_id},
            )
            session.execute(
                text(
                    "UPDATE documents "
                    "SET status = 'ready', page_count = :pages, file_size = :size "
                    "WHERE id = :doc_id"
                ),
                {"pages": processed.page_count, "size": len(file_bytes), "doc_id": document_id},
            )
            session.commit()

        logger.info("Ingestion job %s completed in %.2fs", job_id, elapsed)
        return indexed_count

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        failed_at = datetime.now(UTC)
        error_msg = str(exc)
        logger.exception("Ingestion job %s failed: %s", job_id, error_msg)

        with SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE ingestion_jobs "
                    "SET status = 'failed', completed_at = :now, elapsed_seconds = :elapsed, error_details = :err "
                    "WHERE id = :job_id"
                ),
                {"now": failed_at, "elapsed": elapsed, "err": error_msg, "job_id": job_id},
            )
            session.execute(
                text(
                    "UPDATE documents SET status = 'failed', error_message = :err WHERE id = :doc_id"
                ),
                {"err": error_msg, "doc_id": document_id},
            )
            session.commit()
        raise


__all__ = ["process_index_document"]
