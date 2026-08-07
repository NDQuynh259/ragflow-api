"""DocumentChunk domain entity."""
from sqlalchemy import Column, String, Integer, ForeignKey, Text, JSON, Index, text
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.storage.database.postgres import Base
from app.core.config import settings
from app.domain.mixins import IdentifierMixin, AuditMixin


class DocumentChunk(IdentifierMixin, AuditMixin, Base):
    __tablename__ = "document_chunks"

    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_embedding_hnsw", "embedding",
              postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
