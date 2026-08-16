"""Database access for multimodal document nodes."""

from sqlalchemy.orm import Session

from app.domain.document_node import DocumentNode


class NodeRepository:
    @staticmethod
    def get_by_document(db: Session, document_id: str) -> list[DocumentNode]:
        return (
            db.query(DocumentNode)
            .filter(DocumentNode.document_id == document_id)
            .order_by(DocumentNode.node_index)
            .all()
        )
