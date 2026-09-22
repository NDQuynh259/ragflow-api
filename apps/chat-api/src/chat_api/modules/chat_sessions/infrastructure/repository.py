"""SQLAlchemy implementation of ChatSessionRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from chat_api.modules.chat_sessions.domain.entity import ChatSession as DomainSession
from chat_api.modules.chat_sessions.domain.repository import ChatSessionRepository
from chat_api.modules.chat_sessions.infrastructure.model import (
    ChatSession as ORMSession,
    SessionDocument as ORMSessionDoc,
)


class SqlAlchemyChatSessionRepository(ChatSessionRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, session_id: uuid.UUID) -> DomainSession | None:
        orm = (
            self.session.query(ORMSession)
            .filter(ORMSession.id == session_id, ORMSession.deleted_at.is_(None))
            .first()
        )
        if not orm:
            return None
        return self._to_domain(orm)

    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainSession]:
        query = self.session.query(ORMSession).filter(
            ORMSession.workspace_id == workspace_id,
            ORMSession.deleted_at.is_(None),
        )
        if user_id:
            query = query.filter(ORMSession.user_id == user_id)

        orms = query.order_by(ORMSession.created_at.desc()).offset(offset).limit(limit).all()
        return [self._to_domain(o) for o in orms]

    def save(self, session: DomainSession) -> DomainSession:
        orm = self.session.query(ORMSession).filter(ORMSession.id == session.id).first()
        if not orm:
            orm = ORMSession(
                id=session.id,
                workspace_id=session.workspace_id,
                user_id=session.user_id,
                title=session.title,
                rag_config=session.rag_config,
                deleted_at=session.deleted_at,
            )
            self.session.add(orm)
        else:
            orm.title = session.title
            orm.rag_config = session.rag_config
            orm.deleted_at = session.deleted_at

        # Synchronize attached documents
        current_docs = (
            self.session.query(ORMSessionDoc).filter(ORMSessionDoc.session_id == session.id).all()
        )
        current_doc_ids = {sd.document_id for sd in current_docs}
        target_doc_ids = set(session.attached_document_ids)

        for doc_id in target_doc_ids - current_doc_ids:
            self.session.add(ORMSessionDoc(session_id=session.id, document_id=doc_id))

        for sd in current_docs:
            if sd.document_id not in target_doc_ids:
                self.session.delete(sd)

        return session

    def delete(self, session_id: uuid.UUID) -> bool:
        orm = self.session.query(ORMSession).filter(ORMSession.id == session_id).first()
        if not orm:
            return False
        orm.deleted_at = datetime.now(UTC)
        return True

    def _to_domain(self, orm: ORMSession) -> DomainSession:
        attached_ids = [
            sd.document_id
            for sd in self.session.query(ORMSessionDoc.document_id)
            .filter(ORMSessionDoc.session_id == orm.id)
            .all()
        ]

        return DomainSession(
            id=orm.id,
            workspace_id=orm.workspace_id,
            user_id=orm.user_id,
            title=orm.title,
            rag_config=orm.rag_config or {},
            deleted_at=orm.deleted_at,
            attached_document_ids=attached_ids,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
