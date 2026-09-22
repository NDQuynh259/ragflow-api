"""Centralised Domain → DTO mapping for the Documents module.

Having a single mapper eliminates duplication across command and query handlers
and makes it easy to evolve the DTO shape in one place.
"""

from __future__ import annotations

from chat_api.modules.documents.application.dtos import DocumentDTO, IngestionJobDTO
from chat_api.modules.documents.domain.entity import Document


class DocumentMapper:
    """Maps Document aggregate → DocumentDTO."""

    @staticmethod
    def to_dto(doc: Document) -> DocumentDTO:
        return DocumentDTO(
            id=doc.id,
            workspace_id=doc.workspace_id,
            filename=str(doc.filename),
            content_hash=str(doc.content_hash),
            mime_type=str(doc.mime_type),
            file_size=doc.file_size,
            status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            error_code=doc.error_code,
            error_message=doc.error_message,
            page_count=doc.page_count,
            metadata=doc.metadata,
            jobs=[
                IngestionJobDTO(
                    id=j.id,
                    document_id=j.document_id,
                    status=j.status.value if hasattr(j.status, "value") else str(j.status),
                    retry_count=j.retry_count,
                    parser_name=j.parser_name,
                    chunker_name=j.chunker_name,
                    elapsed_seconds=j.elapsed_seconds,
                    started_at=j.started_at,
                    completed_at=j.completed_at,
                )
                for j in doc.jobs
            ],
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
