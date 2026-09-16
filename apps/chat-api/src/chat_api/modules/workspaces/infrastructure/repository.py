"""SQLAlchemy implementation of WorkspaceRepository."""

from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from chat_api.modules.workspaces.domain.entity import (
    Workspace as DomainWorkspace,
    WorkspaceMember as DomainMember,
    WorkspaceRole,
)
from chat_api.modules.workspaces.domain.repository import WorkspaceRepository
from chat_api.modules.workspaces.infrastructure.models import (
    Permission as ORMPermission,
    RolePermission as ORMRolePermission,
    Workspace as ORMWorkspace,
    WorkspaceMember as ORMMember,
)
from chat_api.shared.application.authorization import effective_permissions


class SqlAlchemyWorkspaceRepository(WorkspaceRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, workspace_id: uuid.UUID) -> DomainWorkspace | None:
        orm = self.session.query(ORMWorkspace).filter(ORMWorkspace.id == workspace_id).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def get_by_slug(self, slug: str) -> DomainWorkspace | None:
        orm = self.session.query(ORMWorkspace).filter(ORMWorkspace.slug == slug).first()
        if not orm:
            return None
        return self._to_domain(orm)

    def list_by_user_id(self, user_id: uuid.UUID) -> list[DomainWorkspace]:
        orms = (
            self.session.query(ORMWorkspace)
            .join(ORMMember, ORMMember.workspace_id == ORMWorkspace.id)
            .filter(ORMMember.user_id == user_id)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def get_member_role(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        return self.session.scalar(
            select(ORMMember.role).where(
                ORMMember.workspace_id == workspace_id,
                ORMMember.user_id == user_id,
            )
        )

    def list_permissions(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> frozenset[str]:
        role = self.get_member_role(workspace_id, user_id)
        if not role:
            return frozenset()

        stored_permission_codes = self.session.scalars(
            select(ORMPermission.code)
            .join(
                ORMRolePermission,
                ORMRolePermission.permission_code == ORMPermission.code,
            )
            .where(
                ORMRolePermission.role_code == role,
            )
        ).all()
        return effective_permissions(role, stored_permission_codes)

    def has_permission(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        permission_code: str,
    ) -> bool:
        perms = self.list_permissions(workspace_id, user_id)
        return "*" in perms or permission_code in perms

    def save(self, workspace: DomainWorkspace) -> DomainWorkspace:
        orm = self.session.query(ORMWorkspace).filter(ORMWorkspace.id == workspace.id).first()
        if not orm:
            orm = ORMWorkspace(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                settings=workspace.settings,
            )
            for m in workspace.members:
                orm.members.append(
                    ORMMember(
                        id=m.id,
                        workspace_id=workspace.id,
                        user_id=m.user_id,
                        role=m.role.value if hasattr(m.role, "value") else str(m.role),
                    )
                )
            self.session.add(orm)
        else:
            orm.name = workspace.name
            orm.slug = workspace.slug
            orm.settings = workspace.settings
            existing_member_ids = {m.id for m in orm.members}
            for m in workspace.members:
                if m.id not in existing_member_ids:
                    orm.members.append(
                        ORMMember(
                            id=m.id,
                            workspace_id=workspace.id,
                            user_id=m.user_id,
                            role=m.role.value if hasattr(m.role, "value") else str(m.role),
                        )
                    )
        return workspace

    def _to_domain(self, orm: ORMWorkspace) -> DomainWorkspace:
        members = [
            DomainMember(
                id=m.id,
                workspace_id=m.workspace_id,
                user_id=m.user_id,
                role=WorkspaceRole(m.role) if m.role in WorkspaceRole._value2member_map_ else WorkspaceRole.MEMBER,
                created_at=m.created_at,
            )
            for m in orm.members
        ]
        return DomainWorkspace(
            id=orm.id,
            name=orm.name,
            slug=orm.slug,
            settings=orm.settings or {},
            members=members,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
