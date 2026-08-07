"""Chunk repository for direct DB access."""
from sqlalchemy.orm import Session
from app.domain.chunk import DocumentChunk


class ChunkRepository:
    @staticmethod
    def get_by_document(db: Session, document_id: str) -> list[DocumentChunk]:
        return db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()
