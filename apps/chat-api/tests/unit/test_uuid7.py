"""Unit tests for RFC 9562 UUIDv7 generator."""

import time
import uuid

from core.uuid7 import uuid7, uuid7_str


def test_uuid7_properties() -> None:
    """Validate RFC 9562 compliance for UUIDv7."""
    u = uuid7()

    # Must be standard uuid.UUID instance
    assert isinstance(u, uuid.UUID)

    # Must be 128 bits
    assert len(u.bytes) == 16

    # Version nibble must be 7
    assert u.version == 7

    # Variant must be RFC 4122 / RFC 9562
    assert u.variant == uuid.RFC_4122


def test_uuid7_str() -> None:
    """Validate string representation format."""
    s = uuid7_str()
    assert isinstance(s, str)
    assert len(s) == 36
    assert s[14] == "7"  # 13th hex char is version: xxxxxxxx-xxxx-7xxx-xxxx-xxxxxxxxxxxx

    # Must round-trip parse
    u = uuid.UUID(s)
    assert u.version == 7


def test_uuid7_monotonic_time_ordering() -> None:
    """Validate time-ordered k-sortable property."""
    ids = []
    for _ in range(5):
        ids.append(uuid7())
        time.sleep(0.002)  # 2ms step to ensure strictly increasing millisecond timestamp

    # Strictly monotonically increasing
    for i in range(len(ids) - 1):
        assert ids[i] < ids[i + 1], f"UUID {ids[i]} should be < {ids[i+1]}"


def test_domain_entities_eager_uuid7_generation() -> None:
    """Validate Pattern B: Domain entities eagerly auto-generate UUIDv7 IDs for CQRS / Event-Driven."""
    from chat_api.modules.workspaces.domain.entity import Workspace
    from chat_api.modules.users.domain.entity import User
    from chat_api.modules.documents.domain.entity import Document
    from chat_api.modules.chat_sessions.domain.entity import ChatSession
    from chat_api.modules.messages.domain.entity import Message, MessageRole

    ws = Workspace(name="AI Lab", slug="ai-lab")
    assert isinstance(ws.id, uuid.UUID)
    assert ws.id.version == 7

    user = User(email="test@domain.com")
    assert isinstance(user.id, uuid.UUID)
    assert user.id.version == 7

    doc = Document(workspace_id=ws.id, filename="paper.pdf", storage_uri="s3://...", content_hash="abc")
    assert isinstance(doc.id, uuid.UUID)
    assert doc.id.version == 7

    job = doc.create_ingestion_job()
    assert isinstance(job.id, uuid.UUID)
    assert job.id.version == 7

    session = ChatSession(workspace_id=ws.id)
    assert isinstance(session.id, uuid.UUID)
    assert session.id.version == 7

    msg = Message(session_id=session.id, role=MessageRole.USER, content="Hello")
    assert isinstance(msg.id, uuid.UUID)
    assert msg.id.version == 7


def test_uuid_primary_key_mixin_dual_generation() -> None:
    """Validate Pattern B: ORM model supports both client-side default and server_default."""
    from core.database import UUIDPrimaryKeyMixin
    from chat_api.modules.workspaces.infrastructure.models import Workspace

    # Verify column has both Python default and database server_default
    id_col = Workspace.__table__.c.id
    assert id_col.default is not None
    assert id_col.server_default is not None
    assert "uuid_generate_v7()" in str(id_col.server_default.arg)

