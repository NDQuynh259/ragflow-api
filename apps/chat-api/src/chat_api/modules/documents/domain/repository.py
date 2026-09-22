"""Document Repository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from chat_api.modules.documents.domain.entity import Document
from chat_api.modules.documents.domain.value_objects import ContentHash


class DocumentRepository(ABC):
    @abstractmethod
    def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        pass

    @abstractmethod
    def get_by_content_hash(
        self, workspace_id: uuid.UUID, content_hash: ContentHash
    ) -> Document | None:
        pass

    @abstractmethod
    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        pass

    @abstractmethod
    def get_ready_documents_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[Document]:
        pass

    @abstractmethod
    def save(self, document: Document) -> Document:
        pass

    @abstractmethod
    def delete(self, document_id: uuid.UUID) -> bool:
        pass
