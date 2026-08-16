"""Persisted multimodal nodes produced by document ingestion."""

from sqlalchemy import Column, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.domain.mixins import AuditMixin, IdentifierMixin
from app.storage.database.postgres import Base


class DocumentNode(IdentifierMixin, AuditMixin, Base):
    """A retrievable text, table, image, or chart unit within a document."""

    __tablename__ = "document_nodes"

    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String, ForeignKey("document_nodes.id", ondelete="SET NULL"), nullable=True)
    node_type = Column(String(20), nullable=False)
    node_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False, default="", server_default=text("''"))
    structured_data = Column(JSON, nullable=True)
    object_key = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=True)
    vision_embedding = Column(Vector(768), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))

    document = relationship("Document", back_populates="nodes")
    parent = relationship("DocumentNode", remote_side="DocumentNode.id")

    __table_args__ = (
        Index("ix_document_nodes_document_id", "document_id"),
        Index("ix_document_nodes_document_id_node_index", "document_id", "node_index"),
        Index(
            "ix_document_nodes_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
