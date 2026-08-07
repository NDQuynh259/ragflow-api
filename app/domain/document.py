"""Document domain entity."""
from sqlalchemy import Column, String, Integer, Text, text
from sqlalchemy.orm import relationship
from app.storage.database.postgres import Base
from app.domain.mixins import IdentifierMixin, AuditMixin


class Document(IdentifierMixin, AuditMixin, Base):
    __tablename__ = "documents"

    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False, default=0, server_default=text("0"))
    chunk_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
