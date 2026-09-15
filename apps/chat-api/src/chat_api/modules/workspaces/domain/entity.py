"""Workspace Domain Aggregate and Entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid

from chat_api.shared.domain.base_entity import AggregateRoot, Entity
from chat_api.shared.domain.uuid7 import uuid7


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


@dataclass(kw_only=True)
class WorkspaceMember(Entity[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole = WorkspaceRole.MEMBER


@dataclass(kw_only=True)
class Workspace(AggregateRoot[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    name: str
    slug: str
    settings: dict = field(default_factory=dict)
    members: list[WorkspaceMember] = field(default_factory=list)

    def is_member(self, user_id: uuid.UUID) -> bool:
        return any(m.user_id == user_id for m in self.members)

    def get_member_role(self, user_id: uuid.UUID) -> WorkspaceRole | None:
        for m in self.members:
            if m.user_id == user_id:
                return m.role
        return None
