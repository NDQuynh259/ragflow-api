"""Document indexing command and handler for worker service."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from core.cqrs import Command, command_handler
from core.database import UnitOfWork
from core.exceptions import EntityNotFoundException
from core.storage import ObjectStoragePort
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexDocumentCommand(Command[int]):
    """Command carrying parameters to ingest, chunk, embed, and index a document."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    storage_uri: str
    user_id: uuid.UUID | None = None


@command_handler(IndexDocumentCommand)
class IndexDocumentHandler:
    """Worker handler executing document ingestion with Atomic State Gate and Idempotent Upsert."""

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
            "Worker starting ingestion for document %s (job: %s, workspace: %s, user: %s)",
            cmd.document_id,
            cmd.job_id,
            cmd.workspace_id,
            cmd.user_id,
        )
        start_time = time.monotonic()
        now_utc = datetime.now(UTC)

        with self.uow:
            session = self.uow.session
            if session is None:
                raise RuntimeError("UnitOfWork session is not initialized")

            # 1. Atomic State Gate: Transition from queued/pending/failed to 'running'
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

            # 2. Account & Workspace Security Gate: verify active status
            ws_row = session.execute(
                text("SELECT id FROM workspaces WHERE id = :ws_id"),
                {"ws_id": cmd.workspace_id},
            ).fetchone()
            if not ws_row:
                session.execute(
                    text(
                        "UPDATE ingestion_jobs "
                        "SET status = 'failed', completed_at = :now, error_details = 'WORKSPACE_NOT_FOUND' "
                        "WHERE id = :job_id"
                    ),
                    {"now": now_utc, "job_id": cmd.job_id},
                )
                self.uow.commit()
                raise EntityNotFoundException("Workspace", cmd.workspace_id)

            if cmd.user_id is not None:
                user_row = session.execute(
                    text("SELECT is_active FROM users WHERE id = :user_id"),
                    {"user_id": cmd.user_id},
                ).fetchone()
                if not user_row or not user_row[0]:
                    session.execute(
                        text(
                            "UPDATE ingestion_jobs "
                            "SET status = 'failed', completed_at = :now, error_details = 'USER_ACCOUNT_SUSPENDED' "
                            "WHERE id = :job_id"
                        ),
                        {"now": now_utc, "job_id": cmd.job_id},
                    )
                    session.execute(
                        text(
                            "UPDATE documents "
                            "SET status = 'failed', error_message = 'User account is inactive or suspended' "
                            "WHERE id = :doc_id"
                        ),
                        {"doc_id": cmd.document_id},
                    )
                    self.uow.commit()
                    from core.exceptions import AccountSuspendedException

                    logger.warning(
                        "Security Gate: User %s is inactive/suspended. Aborting ingestion job %s.",
                        cmd.user_id,
                        cmd.job_id,
                    )
                    raise AccountSuspendedException(
                        f"User '{cmd.user_id}' is inactive or suspended.",
                        details={"user_id": str(cmd.user_id), "job_id": str(cmd.job_id)},
                    )

            # 3. Fetch document metadata
            doc_row = session.execute(
                text(
                    "SELECT id, filename, storage_uri, status "
                    "FROM documents WHERE id = :doc_id AND deleted_at IS NULL"
                ),
                {"doc_id": cmd.document_id},
            ).fetchone()
            if not doc_row:
                raise EntityNotFoundException("Document", cmd.document_id)

            filename = str(doc_row[1])

            # Mark document processing
            session.execute(
                text("UPDATE documents SET status = 'processing' WHERE id = :doc_id"),
                {"doc_id": cmd.document_id},
            )
            self.uow.commit()

        # Ingestion pipeline outside of lock/transaction
        try:
            # 3. Read raw file bytes from storage
            file_bytes = self.storage.get(cmd.storage_uri)
            logger.info("Read %d bytes from storage URI: %s", len(file_bytes), cmd.storage_uri)

            # 4. Parse & chunk document
            processed = self.pipeline.process(
                file_bytes,
                filename=filename,
                document_id=str(cmd.document_id),
            )
            logger.info(
                "Processed document %s: %d pages, %d chunks",
                cmd.document_id,
                processed.page_count,
                len(processed.chunks),
            )

            # 5. Attach workspace_id to each chunk
            for chunk in processed.chunks:
                chunk.workspace_id = str(cmd.workspace_id)

            # 6. Embed and index chunks into vector store (Idempotent upsert)
            indexed_count = self.engine.index(processed.chunks)
            logger.info(
                "Successfully indexed %d chunks for document %s",
                indexed_count,
                cmd.document_id,
            )

            # 7. Mark job completed and document ready
            elapsed = time.monotonic() - start_time
            completed_at = datetime.now(UTC)

            with self.uow:
                session = self.uow.session
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
                with self.uow:
                    session = self.uow.session
                    if session is not None:
                        session.execute(
                            text(
                                "UPDATE ingestion_jobs "
                                "SET status = 'failed', completed_at = :now, "
                                "elapsed_seconds = :elapsed, error_details = :err "
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
                                "UPDATE documents SET status = 'failed', error_message = :err "
                                "WHERE id = :doc_id"
                            ),
                            {"err": error_msg, "doc_id": cmd.document_id},
                        )
                        self.uow.commit()
            except Exception:
                logger.warning("Failed to record failure status for job %s", cmd.job_id)
            raise


__all__ = [
    "IndexDocumentCommand",
    "IndexDocumentHandler",
]
