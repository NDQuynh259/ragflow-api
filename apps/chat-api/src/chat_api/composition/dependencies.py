"""Composition Root — centralised dependency providers.

All concrete adapter instantiation and UnitOfWork repository registrations happen
here so that presentation routers and application handlers only depend on abstract
ports and interfaces, never on concrete implementations.
"""

from __future__ import annotations

from chat_api.modules.auth.domain.repository import UserSessionRepository
from chat_api.modules.auth.infrastructure.repository import (
    SqlAlchemyUserSessionRepository,
)
from chat_api.modules.chat_sessions.domain.repository import ChatSessionRepository
from chat_api.modules.chat_sessions.infrastructure.repository import (
    SqlAlchemyChatSessionRepository,
)
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.modules.documents.infrastructure.repository import (
    SqlAlchemyDocumentRepository,
)
from chat_api.modules.messages.domain.repository import MessageRepository
from chat_api.modules.messages.infrastructure.repository import (
    SqlAlchemyMessageRepository,
)
from chat_api.modules.users.domain.repository import UserRepository
from chat_api.modules.users.infrastructure.repository import (
    SqlAlchemyUserRepository,
)
from chat_api.modules.workspaces.domain.repository import WorkspaceRepository
from chat_api.modules.workspaces.infrastructure.repository import (
    SqlAlchemyWorkspaceRepository,
)
from chat_api.shared.infrastructure.database.uow import register_repository
from chat_api.shared.infrastructure.rag import RAGEngineAdapter, RAGEnginePort
from core.queue.background import BackgroundQueueAdapter
from core.queue.port import IngestionQueuePort
from core.storage.local import LocalStorageAdapter
from core.storage.port import ObjectStoragePort

# Ensure domain event handlers are registered to EventBus
import chat_api.modules.documents.application.event_handlers  # noqa: F401

# ---------------------------------------------------------------------------
# Singleton adapter instances (created once at import time)
# ---------------------------------------------------------------------------
_storage = LocalStorageAdapter()
_queue = BackgroundQueueAdapter()
_rag_engine = RAGEngineAdapter()


# ---------------------------------------------------------------------------
# UnitOfWork Repository Registrations
# Composition Root binds abstract interfaces to concrete SQLAlchemy implementations
# ---------------------------------------------------------------------------
register_repository(
    DocumentRepository,
    SqlAlchemyDocumentRepository,
    aliases="documents",
)
register_repository(
    ChatSessionRepository,
    SqlAlchemyChatSessionRepository,
    aliases=["chat_sessions", "sessions"],
)
register_repository(
    MessageRepository,
    SqlAlchemyMessageRepository,
    aliases="messages",
)
register_repository(
    UserRepository,
    SqlAlchemyUserRepository,
    aliases="users",
)
register_repository(
    WorkspaceRepository,
    SqlAlchemyWorkspaceRepository,
    aliases="workspaces",
)
register_repository(
    UserSessionRepository,
    SqlAlchemyUserSessionRepository,
    aliases="user_sessions",
)


# ---------------------------------------------------------------------------
# FastAPI dependency callables — return abstract port types
# ---------------------------------------------------------------------------
def get_storage() -> ObjectStoragePort:
    """Provide the application-wide object storage adapter."""
    return _storage


def get_queue() -> IngestionQueuePort:
    """Provide the application-wide ingestion queue adapter."""
    return _queue


def get_rag_engine() -> RAGEnginePort:
    """Provide the application-wide RAG engine adapter."""
    return _rag_engine


__all__ = [
    "get_storage",
    "get_queue",
    "get_rag_engine",
]
