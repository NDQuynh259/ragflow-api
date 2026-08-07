"""Database access for documents."""

from sqlalchemy.orm import Session

from app.domain.document import Document


class DocumentRepository:
    @staticmethod
    def add(db: Session, document: Document) -> None:
        db.add(document)

    @staticmethod
    def list_all(db: Session) -> list[Document]:
        return db.query(Document).order_by(Document.created_at.desc()).all()

    @staticmethod
    def get_by_id(db: Session, document_id: str) -> Document | None:
        return db.query(Document).filter(Document.id == document_id).first()

    @staticmethod
    def delete(db: Session, document: Document) -> None:
        db.delete(document)
