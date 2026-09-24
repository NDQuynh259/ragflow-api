"""Shared test fixtures and in-memory test doubles for Modular Monolith."""

import uuid

import pytest

# Ensure domain event handlers are registered to EventBus
import chat_api.modules.documents.application.event_handlers  # noqa: F401
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.domain.repository import UserSessionRepository
from chat_api.modules.chat_sessions.domain.entity import ChatSession
from chat_api.modules.chat_sessions.domain.repository import ChatSessionRepository
from chat_api.modules.documents.domain.entity import Document, DocumentStatus
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.modules.messages.domain.entity import Message
from chat_api.modules.messages.domain.repository import MessageRepository
from chat_api.modules.users.domain.entity import User
from chat_api.modules.users.domain.repository import UserRepository
from chat_api.modules.workspaces.domain.entity import Workspace
from chat_api.modules.workspaces.domain.repository import WorkspaceRepository
from chat_api.shared.auth import Permission, get_permissions_for_role
from chat_api.shared.infrastructure.database import UnitOfWork
from chat_api.shared.infrastructure.rag import RAGEnginePort
from core.queue import IngestionQueuePort
from core.storage import ObjectStoragePort


class InMemoryWorkspaceRepo(WorkspaceRepository):
    def __init__(self):
        self.data: dict[uuid.UUID, Workspace] = {}

    def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        return self.data.get(workspace_id)

    def get_by_slug(self, slug: str) -> Workspace | None:
        return next((w for w in self.data.values() if w.slug == slug), None)

    def list_by_user_id(self, user_id: uuid.UUID) -> list[Workspace]:
        return [w for w in self.data.values() if w.is_member(user_id)]

    def get_member_role(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        workspace = self.get_by_id(workspace_id)
        if workspace is None:
            return None
        role = workspace.get_member_role(user_id)
        return role.value if role is not None else None

    def list_permissions(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> frozenset[str]:
        permissions = get_permissions_for_role(self.get_member_role(workspace_id, user_id))
        if "*" in permissions:
            return frozenset(permission.value for permission in Permission)
        return permissions

    def has_permission(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        permission_code: str,
    ) -> bool:
        return permission_code in self.list_permissions(workspace_id, user_id)

    def save(self, workspace: Workspace) -> Workspace:
        self.data[workspace.id] = workspace
        return workspace


class InMemoryDocRepo(DocumentRepository):
    def __init__(self):
        self.data: dict[uuid.UUID, Document] = {}

    def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self.data.get(document_id)

    def get_by_content_hash(self, workspace_id: uuid.UUID, content_hash: str) -> Document | None:
        return next(
            (
                d
                for d in self.data.values()
                if d.workspace_id == workspace_id and d.content_hash == content_hash
            ),
            None,
        )

    def list_by_workspace(
        self, workspace_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        return [d for d in self.data.values() if d.workspace_id == workspace_id]

    def get_ready_documents_by_ids(
        self, workspace_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> list[Document]:
        return [
            d
            for d in self.data.values()
            if d.workspace_id == workspace_id
            and d.id in document_ids
            and d.status == DocumentStatus.READY
        ]

    def save(self, document: Document) -> Document:
        self.data[document.id] = document
        return document

    def delete(self, document_id: uuid.UUID) -> bool:
        if document_id in self.data:
            del self.data[document_id]
            return True
        return False

    def update_storage_uri(self, old_uri: str, new_uri: str) -> bool:
        from chat_api.modules.documents.domain.value_objects import StorageUri

        updated = False
        for doc in self.data.values():
            if str(doc.storage_uri) == old_uri:
                doc.storage_uri = StorageUri(new_uri)
                updated = True
        return updated


class InMemorySessionRepo(ChatSessionRepository):
    def __init__(self):
        self.data: dict[uuid.UUID, ChatSession] = {}

    def get_by_id(self, session_id: uuid.UUID) -> ChatSession | None:
        return self.data.get(session_id)

    def list_by_workspace(
        self, workspace_id: uuid.UUID, user_id=None, limit: int = 50, offset: int = 0
    ) -> list[ChatSession]:
        return [s for s in self.data.values() if s.workspace_id == workspace_id]

    def save(self, session: ChatSession) -> ChatSession:
        self.data[session.id] = session
        return session

    def delete(self, session_id: uuid.UUID) -> bool:
        if session_id in self.data:
            del self.data[session_id]
            return True
        return False


class InMemoryMessageRepo(MessageRepository):
    def __init__(self):
        self.data: dict[uuid.UUID, Message] = {}

    def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        return self.data.get(message_id)

    def list_by_session(
        self, session_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[Message]:
        return [m for m in self.data.values() if m.session_id == session_id]

    def save(self, message: Message) -> Message:
        self.data[message.id] = message
        return message


class InMemoryUserRepo(UserRepository):
    def __init__(self):
        self.data: dict[uuid.UUID, User] = {}

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.data.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.data.values() if u.email == email), None)

    def save(self, user: User) -> User:
        self.data[user.id] = user
        return user


class InMemoryUserSessionRepo(UserSessionRepository):
    def __init__(self):
        self.data: dict[str, UserSession] = {}

    def get_by_token(self, token: str) -> UserSession | None:
        return self.data.get(token)

    def save(self, session: UserSession) -> UserSession:
        self.data[session.token] = session
        return session

    def delete_by_token(self, token: str) -> bool:
        if token in self.data:
            del self.data[token]
            return True
        return False

    def delete_by_user_id(self, user_id: uuid.UUID) -> int:
        to_del = [t for t, s in self.data.items() if s.user_id == user_id]
        for t in to_del:
            del self.data[t]
        return len(to_del)


class FakeUnitOfWork(UnitOfWork):
    def __init__(self):
        self.workspaces = InMemoryWorkspaceRepo()
        self.documents = InMemoryDocRepo()
        self.chat_sessions = InMemorySessionRepo()
        self.sessions = self.chat_sessions
        self.messages = InMemoryMessageRepo()
        self.users = InMemoryUserRepo()
        self.user_sessions = InMemoryUserSessionRepo()
        self.committed = False
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.committed = True
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def get_repo(self, repo_cls):
        from chat_api.modules.auth.domain.repository import UserSessionRepository
        from chat_api.modules.chat_sessions.domain.repository import ChatSessionRepository
        from chat_api.modules.documents.domain.repository import DocumentRepository
        from chat_api.modules.messages.domain.repository import MessageRepository
        from chat_api.modules.users.domain.repository import UserRepository
        from chat_api.modules.workspaces.domain.repository import WorkspaceRepository

        mapping = {
            DocumentRepository: self.documents,
            ChatSessionRepository: self.chat_sessions,
            MessageRepository: self.messages,
            UserRepository: self.users,
            WorkspaceRepository: self.workspaces,
            UserSessionRepository: self.user_sessions,
        }
        if repo_cls in mapping:
            return mapping[repo_cls]
        return super().get_repo(repo_cls)


class FakeStorage(ObjectStoragePort):
    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        return f"fake://{workspace_id}/{filename}"

    def get(self, storage_uri: str) -> bytes:
        return b"content"

    def delete(self, storage_uri: str) -> bool:
        return True

    def exists(self, storage_uri: str) -> bool:
        return True

    def get_size(self, storage_uri: str) -> int:
        return 7


class FakeQueue(IngestionQueuePort):
    def __init__(self):
        self.enqueued = []
        self.raw_jobs = []

    def enqueue(self, action: str, payload: dict, job_id=None, routing_key=None) -> str:
        jid = str(job_id or uuid.uuid4())
        self.raw_jobs.append((action, payload, jid, routing_key))
        return jid

    def enqueue_ingestion(self, document_id, job_id, storage_uri, workspace_id):
        self.enqueued.append((document_id, job_id, storage_uri, workspace_id))


class FakeRAGEngine(RAGEnginePort):
    def answer(self, query: str, document_ids=None, top_k=None):
        citations = []
        if document_ids:
            citations.append(
                {
                    "document_id": document_ids[0],
                    "chunk_id": "chunk_1",
                    "page_number": 1,
                    "bbox": [0.1, 0.1, 0.5, 0.5],
                    "quote": "Trích dẫn tài liệu",
                    "relevance_score": 0.95,
                }
            )
        return "Câu trả lời RAG test", citations, {"prompt_tokens": 10, "completion_tokens": 20}


@pytest.fixture
def fake_uow():
    return FakeUnitOfWork()


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def fake_queue():
    return FakeQueue()


@pytest.fixture
def fake_rag():
    return FakeRAGEngine()
