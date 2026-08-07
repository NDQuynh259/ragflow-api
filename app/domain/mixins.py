"""Shared identifier and audit mixins for domain entities."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, text


class IdentifierMixin:
    """Common primary-key field for persisted entities."""
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))


class AuditMixin:
    """Common creation, update, and soft-delete audit fields."""
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
