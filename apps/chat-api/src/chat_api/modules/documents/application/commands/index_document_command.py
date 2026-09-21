"""Index Document Command and Handler for background worker ingestion."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.shared.bus import Command, command_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import EntityNotFoundException
from core.storage import ObjectStoragePort
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexDocumentCommand(Command[int]):
    """CQRS Command to ingest, parse, chunk, embed, and index a document."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    storage_uri: str


@command_handler(IndexDocumentCommand)
class IndexDocumentHandler:
    """CQRS Handler executing document ingestion with Atomic State Gate and Idempotent Upsert."""

    def __init__(
        self,
        uow: UnitOfWork,
        storage: ObjectStoragePort,
        pipeline: DocumentPipeline | None = None,
        engine: RAGEngine | None = None,
    ) -> None:
        self.uow = uow
        self.storage = storage
        self.pipeline = pipeline or DocumentPipeline()
        self.engine = engine or RAGEngine.from_env()

    def handle(self, cmd: IndexDocumentCommand) -> int:
        logger.info(
            "Starting ingestion handler for document %s (job: %s, workspace: %s)",
            cmd.document_id,
            cmd.job_id,
            cmd.workspace_id,
        )
        start_time = time.monotonic()
        now_utc = datetime.now(UTC)

        session = getattr(self.uow, "session", None)

        # 1. Atomic State Gate: Transition from queued/pending/failed to 'running'
        if session is not None:
            result = session.execute(
                text(
                    "UPDATE ingestion_jobs "
                    "SET status = 'running', started_at = :now "
                    "WHERE id = :job_id AND status IN ('queued', 'pending', 'failed')"
                ),
                {"now": now_utc, "job_id": cmd.job_id},
            )
            if getattr(result, "rowcount", -1) == 0:
                row = session.execute(
                    text("SELECT status FROM ingestion_jobs WHERE id = :job_id"),
                    {"job_id": cmd.job_id},
                ).fetchone()
                current_status = row[0] if row else "unknown"
                if current_status in ("running", "completed"):
                    logger.warning(
                        "Job %s is already in status '%s', skipping duplicate execution.",
                        cmd.job_id,
                        current_status,
                    )
                    return 0

        doc_repo = self.uow.get_repo(DocumentRepository)
        doc = doc_repo.get_by_id(cmd.document_id)
        if not doc:
            raise EntityNotFoundException("Document", cmd.document_id)

        doc.mark_processing()
        doc_repo.save(doc)
        self.uow.commit()

        try:
            # 2. Read raw file bytes from storage
            file_bytes = self.storage.get(cmd.storage_uri)
            logger.info("Read %d bytes from storage URI: %s", len(file_bytes), cmd.storage_uri)

            # 3. Parse & chunk document
            processed = self.pipeline.process(
                file_bytes,
                filename=str(doc.filename),
                document_id=str(doc.id),
            )
            logger.info(
                "Processed document %s: %d pages, %d chunks",
                doc.id,
                processed.page_count,
                len(processed.chunks),
            )

            # 4. Attach workspace_id to each chunk
            for chunk in processed.chunks:
                chunk.workspace_id = str(cmd.workspace_id)

            # 5. Embed and index chunks into vector store (Idempotent upsert)
            indexed_count = self.engine.index(processed.chunks)
            logger.info("Successfully indexed %d chunks for document %s", indexed_count, doc.id)

            # 6. Mark job as completed and document as ready
            elapsed = time.monotonic() - start_time
            completed_at = datetime.now(UTC)

            doc.mark_ready(page_count=processed.page_count)
            doc_repo.save(doc)

            if session is not None:
                session.execute(
                    text(
                        "UPDATE ingestion_jobs "
                        "SET status = 'completed', completed_at = :now, elapsed_seconds = :elapsed "
                        "WHERE id = :job_id"
                    ),
                    {"now": completed_at, "elapsed": elapsed, "job_id": cmd.job_id},
                )
                session.execute(
                    text(
                        "UPDATE documents "
                        "SET status = 'ready', page_count = :pages, file_size = :size "
                        "WHERE id = :doc_id"
                    ),
                    {
                        "pages": processed.page_count,
                        "size": len(file_bytes),
                        "doc_id": cmd.document_id,
                    },
                )
            self.uow.commit()

            logger.info("Ingestion job %s completed in %.2fs", cmd.job_id, elapsed)
            return indexed_count

        except Exception as exc:
            elapsed = time.monotonic() - start_time
            failed_at = datetime.now(UTC)
            error_msg = str(exc)
            logger.exception("Ingestion job %s failed: %s", cmd.job_id, error_msg)

            try:
                doc.mark_failed("INGESTION_ERROR", error_msg)
                doc_repo.save(doc)
                if session is not None:
                    session.execute(
                        text(
                            "UPDATE ingestion_jobs "
                            "SET status = 'failed', completed_at = :now, elapsed_seconds = :elapsed, error_details = :err "
                            "WHERE id = :job_id"
                        ),
                        {
                            "now": failed_at,
                            "elapsed": elapsed,
                            "err": error_msg,
                            "job_id": cmd.job_id,
                        },
                    )
                    session.execute(
                        text(
                            "UPDATE documents SET status = 'failed', error_message = :err WHERE id = :doc_id"
                        ),
                        {"err": error_msg, "doc_id": cmd.document_id},
                    )
                self.uow.commit()
            except Exception:
                logger.warning("Failed to record failure status for job %s", cmd.job_id)
            raise
