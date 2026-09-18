"""Centralized model imports for Alembic and metadata reflection."""

from chat_api.modules.auth.infrastructure.model import UserSession
from chat_api.modules.chat_sessions.infrastructure.model import (
    ChatSession,
    SessionDocument,
)
from chat_api.modules.documents.infrastructure.model import Chunk, Document, IngestionJob
from chat_api.modules.messages.infrastructure.model import (
    Message,
    MessageCitation,
    MessageFeedback,
)
from chat_api.modules.users.infrastructure.model import User
from chat_api.modules.workspaces.infrastructure.models import (
    Permission,
    Role,
    RolePermission,
    Workspace,
    WorkspaceMember,
)
from core.database import Base

__all__ = [
    "Base",
    "Workspace",
    "WorkspaceMember",
    "Role",
    "Permission",
    "RolePermission",
    "User",
    "UserSession",
    "Document",
    "IngestionJob",
    "Chunk",
    "ChatSession",
    "SessionDocument",
    "Message",
    "MessageCitation",
    "MessageFeedback",
]
