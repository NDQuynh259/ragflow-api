"""SQLAlchemy implementation of UserSessionRepository."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from chat_api.modules.auth.domain.entity import UserSession as DomainSession
from chat_api.modules.auth.domain.repository import UserSessionRepository
from chat_api.modules.auth.infrastructure.model import UserSession as ORMSession
from core.auth import hash_session_token


class SqlAlchemyUserSessionRepository(UserSessionRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_token(self, token: str) -> DomainSession | None:
        token_hash = hash_session_token(token)
        orm = self.session.query(ORMSession).filter(ORMSession.token_hash == token_hash).first()
        if not orm:
            return None
        return self._to_domain(orm, presented_token=token)

    def save(self, session: DomainSession) -> DomainSession:
        orm = self.session.query(ORMSession).filter(ORMSession.id == session.id).first()
        if not orm:
            orm = ORMSession(
                id=session.id,
                user_id=session.user_id,
                active_workspace_id=session.active_workspace_id,
                token_hash=hash_session_token(session.token),
                expires_at=session.expires_at,
                ip_address=session.ip_address,
                user_agent=session.user_agent,
                created_at=session.created_at,
            )
            self.session.add(orm)
        else:
            orm.active_workspace_id = session.active_workspace_id
            orm.token_hash = hash_session_token(session.token)
            orm.expires_at = session.expires_at
            orm.ip_address = session.ip_address
            orm.user_agent = session.user_agent
        return session

    def delete_by_token(self, token: str) -> bool:
        token_hash = hash_session_token(token)
        deleted = (
            self.session.query(ORMSession)
            .filter(ORMSession.token_hash == token_hash)
            .delete(synchronize_session=False)
        )
        return deleted > 0

    def delete_by_user_id(self, user_id: uuid.UUID) -> int:
        return (
            self.session.query(ORMSession)
            .filter(ORMSession.user_id == user_id)
            .delete(synchronize_session=False)
        )

    def _to_domain(self, orm: ORMSession, presented_token: str) -> DomainSession:
        return DomainSession(
            id=orm.id,
            user_id=orm.user_id,
            active_workspace_id=orm.active_workspace_id,
            token=presented_token,
            expires_at=orm.expires_at,
            ip_address=orm.ip_address,
            user_agent=orm.user_agent,
            created_at=orm.created_at,
        )
