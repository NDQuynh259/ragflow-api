"""SQLAlchemy implementation of DocumentRepository."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from sqlalchemy.orm import Session

from chat_api.modules.documents.domain.entity import (
    Document as DomainDocument,
    DocumentStatus,
    IngestionJob as DomainJob,
    IngestionStatus,
)
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.modules.documents.domain.value_objects import (
    ContentHash,
    Filename,
    MimeType,
    StorageUri,
)
from chat_api.modules.documents.infrastructure.model import (
    Document as ORMDocument,
    IngestionJob as ORMJob,
)


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, document_id: uuid.UUID) -> DomainDocument | None:
        orm = (
            self.session.query(ORMDocument)
            .filter(ORMDocument.id == document_id, ORMDocument.deleted_at.is_(None))
            .first()
        )
        if not orm:
            return None
        return self._to_domain(orm)

    def get_by_content_hash(self, workspace_id: uuid.UUID, content_hash: ContentHash) -> DomainDocument | None:
        orm = (
            self.session.query(ORMDocument)
            .filter(
                ORMDocument.workspace_id == workspace_id,
                ORMDocument.content_hash == str(content_hash),
                ORMDocument.deleted_at.is_(None),
            )
            .first()
        )
        if not orm:
            return None
        return self._to_domain(orm)

    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainDocument]:
        orms = (
            self.session.query(ORMDocument)
            .filter(ORMDocument.workspace_id == workspace_id, ORMDocument.deleted_at.is_(None))
            .order_by(ORMDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def get_ready_documents_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[DomainDocument]:
        if not document_ids:
            return []
        orms = (
            self.session.query(ORMDocument)
            .filter(
                ORMDocument.workspace_id == workspace_id,
                ORMDocument.id.in_(document_ids),
                ORMDocument.status == "ready",
                ORMDocument.deleted_at.is_(None),
            )
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, document: DomainDocument) -> DomainDocument:
        orm = self.session.query(ORMDocument).filter(ORMDocument.id == document.id).first()
        status_val = document.status.value if hasattr(document.status, "value") else str(document.status)

        if not orm:
            orm = ORMDocument(
                id=document.id,
                workspace_id=document.workspace_id,
                filename=str(document.filename),
                storage_uri=str(document.storage_uri),
                content_hash=str(document.content_hash),
                mime_type=str(document.mime_type),
                file_size=document.file_size,
                status=status_val,
                error_code=document.error_code,
                error_message=document.error_message,
                page_count=document.page_count,
                metadata_=document.metadata,
                deleted_at=document.deleted_at,
            )
            self.session.add(orm)
        else:
            orm.filename = str(document.filename)
            orm.status = status_val
            orm.error_code = document.error_code
            orm.error_message = document.error_message
            orm.page_count = document.page_count
            orm.metadata_ = document.metadata
            orm.deleted_at = document.deleted_at

        # Save jobs
        for job in document.jobs:
            orm_job = self.session.query(ORMJob).filter(ORMJob.id == job.id).first()
            job_status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
            if not orm_job:
                orm_job = ORMJob(
                    id=job.id,
                    document_id=job.document_id,
                    status=job_status_val,
                    retry_count=job.retry_count,
                    parser_name=job.parser_name,
                    chunker_name=job.chunker_name,
                    elapsed_seconds=job.elapsed_seconds,
                    error_details=job.error_details,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )
                self.session.add(orm_job)
            else:
                orm_job.status = job_status_val
                orm_job.retry_count = job.retry_count
                orm_job.elapsed_seconds = job.elapsed_seconds
                orm_job.error_details = job.error_details
                orm_job.started_at = job.started_at
                orm_job.completed_at = job.completed_at

        return document

    def delete(self, document_id: uuid.UUID) -> bool:
        orm = self.session.query(ORMDocument).filter(ORMDocument.id == document_id).first()
        if not orm:
            return False
        orm.deleted_at = datetime.now(timezone.utc)
        return True

    def _to_domain(self, orm: ORMDocument) -> DomainDocument:
        jobs = [
            DomainJob(
                id=j.id,
                document_id=j.document_id,
                status=IngestionStatus(j.status) if j.status in IngestionStatus._value2member_map_ else IngestionStatus.QUEUED,
                retry_count=j.retry_count,
                parser_name=j.parser_name,
                chunker_name=j.chunker_name,
                elapsed_seconds=j.elapsed_seconds,
                error_details=j.error_details,
                started_at=j.started_at,
                completed_at=j.completed_at,
                created_at=j.created_at,
            )
            for j in orm.jobs
        ]
        status = DocumentStatus(orm.status) if orm.status in DocumentStatus._value2member_map_ else DocumentStatus.QUEUED

        return DomainDocument(
            id=orm.id,
            workspace_id=orm.workspace_id,
            filename=Filename(orm.filename),
            storage_uri=StorageUri(orm.storage_uri),
            content_hash=ContentHash(orm.content_hash),
            mime_type=MimeType(orm.mime_type),
            file_size=orm.file_size,
            status=status,
            error_code=orm.error_code,
            error_message=orm.error_message,
            page_count=orm.page_count,
            metadata=orm.metadata_ or {},
            deleted_at=orm.deleted_at,
            jobs=jobs,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
