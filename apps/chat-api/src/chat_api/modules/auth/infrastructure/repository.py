"""SQLAlchemy implementation of UserSessionRepository."""

from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from chat_api.modules.auth.domain.entity import UserSession as DomainSession
from chat_api.modules.auth.domain.repository import UserSessionRepository
from chat_api.modules.auth.infrastructure.model import UserSession as ORMSession


class SqlAlchemyUserSessionRepository(UserSessionRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_token(self, token: str) -> DomainSession | None:
        orm = self.session.query(ORMSession).filter(ORMSession.token == token).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def save(self, domain_session: DomainSession) -> DomainSession:
        orm = self.session.query(ORMSession).filter(ORMSession.id == domain_session.id).first()
        if not orm:
            orm = ORMSession(
                id=domain_session.id,
                user_id=domain_session.user_id,
                active_workspace_id=domain_session.active_workspace_id,
                token=domain_session.token,
                expires_at=domain_session.expires_at,
                ip_address=domain_session.ip_address,
                user_agent=domain_session.user_agent,
                created_at=domain_session.created_at,
            )
            self.session.add(orm)
        else:
            orm.active_workspace_id = domain_session.active_workspace_id
            orm.token = domain_session.token
            orm.expires_at = domain_session.expires_at
            orm.ip_address = domain_session.ip_address
            orm.user_agent = domain_session.user_agent
        return domain_session

    def delete_by_token(self, token: str) -> bool:
        deleted = (
            self.session.query(ORMSession)
            .filter(ORMSession.token == token)
            .delete(synchronize_session=False)
        )
        return deleted > 0

    def delete_by_user_id(self, user_id: uuid.UUID) -> int:
        return (
            self.session.query(ORMSession)
            .filter(ORMSession.user_id == user_id)
            .delete(synchronize_session=False)
        )

    def _to_domain(self, orm: ORMSession) -> DomainSession:
        return DomainSession(
            id=orm.id,
            user_id=orm.user_id,
            active_workspace_id=orm.active_workspace_id,
            token=orm.token,
            expires_at=orm.expires_at,
            ip_address=orm.ip_address,
            user_agent=orm.user_agent,
            created_at=orm.created_at,
        )
