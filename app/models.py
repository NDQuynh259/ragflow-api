import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON, Index, text
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import settings

class IdentifierMixin:
    """Common primary-key field for persisted entities."""

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))


class AuditMixin:
    """Common creation, update, and soft-delete audit fields."""

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class Document(IdentifierMixin, AuditMixin, Base):
    __tablename__ = "documents"

    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False, default=0, server_default=text("0"))
    chunk_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(IdentifierMixin, AuditMixin, Base):
    __tablename__ = "document_chunks"

    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::json"),
    )
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
