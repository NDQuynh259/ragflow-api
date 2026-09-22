"""SQLAlchemy implementation of UserRepository."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from chat_api.modules.users.domain.entity import User as DomainUser
from chat_api.modules.users.domain.repository import UserRepository
from chat_api.modules.users.infrastructure.model import User as ORMUser


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: uuid.UUID) -> DomainUser | None:
        orm = self.session.query(ORMUser).filter(ORMUser.id == user_id).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def get_by_email(self, email: str) -> DomainUser | None:
        orm = self.session.query(ORMUser).filter(ORMUser.email == email).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def save(self, user: DomainUser) -> DomainUser:
        orm = self.session.query(ORMUser).filter(ORMUser.id == user.id).first()
        if not orm:
            orm = ORMUser(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                hashed_password=user.hashed_password,
                is_active=user.is_active,
            )
            self.session.add(orm)
        else:
            orm.email = user.email
            orm.full_name = user.full_name
            orm.hashed_password = user.hashed_password
            orm.is_active = user.is_active
        return user

    def _to_domain(self, orm: ORMUser) -> DomainUser:
        return DomainUser(
            id=orm.id,
            email=orm.email,
            full_name=orm.full_name,
            hashed_password=orm.hashed_password,
            is_active=orm.is_active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
