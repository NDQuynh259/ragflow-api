"""SQLAlchemy implementation of MessageRepository."""

from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from chat_api.modules.messages.domain.entity import (
    Message as DomainMessage,
    MessageCitation as DomainCitation,
    MessageFeedback as DomainFeedback,
    MessageRole,
)
from chat_api.modules.messages.domain.repository import MessageRepository
from chat_api.modules.messages.infrastructure.model import (
    Message as ORMMessage,
    MessageCitation as ORMCitation,
    MessageFeedback as ORMFeedback,
)


class SqlAlchemyMessageRepository(MessageRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, message_id: uuid.UUID) -> DomainMessage | None:
        orm = self.session.query(ORMMessage).filter(ORMMessage.id == message_id).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def list_by_session(
        self,
        session_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DomainMessage]:
        orms = (
            self.session.query(ORMMessage)
            .filter(ORMMessage.session_id == session_id)
            .order_by(ORMMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, message: DomainMessage) -> DomainMessage:
        orm = self.session.query(ORMMessage).filter(ORMMessage.id == message.id).first()
        role_val = message.role.value if hasattr(message.role, "value") else str(message.role)

        if not orm:
            orm = ORMMessage(
                id=message.id,
                session_id=message.session_id,
                role=role_val,
                content=message.content,
                prompt_tokens=message.prompt_tokens,
                completion_tokens=message.completion_tokens,
                latency_ms=message.latency_ms,
            )
            self.session.add(orm)
        else:
            orm.content = message.content
            orm.prompt_tokens = message.prompt_tokens
            orm.completion_tokens = message.completion_tokens
            orm.latency_ms = message.latency_ms

        for cit in message.citations:
            orm_cit = self.session.query(ORMCitation).filter(ORMCitation.id == cit.id).first()
            if not orm_cit:
                orm_cit = ORMCitation(
                    id=cit.id,
                    message_id=cit.message_id,
                    chunk_id=cit.chunk_id,
                    document_id=cit.document_id,
                    page_number=cit.page_number,
                    bbox=cit.bbox,
                    quote=cit.quote,
                    relevance_score=cit.relevance_score,
                )
                self.session.add(orm_cit)

        return message

    def _to_domain(self, orm: ORMMessage) -> DomainMessage:
        citations = [
            DomainCitation(
                id=c.id,
                message_id=c.message_id,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                page_number=c.page_number,
                bbox=c.bbox or [],
                quote=c.quote,
                relevance_score=c.relevance_score,
                created_at=c.created_at,
            )
            for c in orm.citations
        ]
        feedbacks = [
            DomainFeedback(
                id=f.id,
                message_id=f.message_id,
                rating=f.rating,
                user_id=f.user_id,
                comment=f.comment,
                created_at=f.created_at,
            )
            for f in orm.feedbacks
        ]
        role = MessageRole(orm.role) if orm.role in MessageRole._value2member_map_ else MessageRole.USER

        return DomainMessage(
            id=orm.id,
            session_id=orm.session_id,
            role=role,
            content=orm.content,
            prompt_tokens=orm.prompt_tokens,
            completion_tokens=orm.completion_tokens,
            latency_ms=orm.latency_ms,
            citations=citations,
            feedbacks=feedbacks,
            created_at=orm.created_at,
        )
