"""Document ingestion use cases."""

import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.domain.document import Document
from app.storage.database.repositories.document import DocumentRepository
from app.storage.vector.pgvector import VectorStoreRepository
from app.ingestion.chunkers.recursive import RecursiveChunker
from app.embeddings.base import EmbeddingService
from app.ingestion.parsers.pdf_parser import DocumentParseError, DocumentParser


class IngestionPipeline:
    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        self.embedder = embedder or EmbeddingService()

    def ingest_file(
        self,
        db: Session,
        *,
        filename: str,
        contents: bytes,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Document:
        filename = DocumentParser.sanitize_text(filename or "upload.txt").strip()
        if not filename:
            raise AppError("Document filename cannot be empty.")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # Validate file extension and size
        if extension not in settings.ALLOWED_FILE_EXTENSIONS:
            raise AppError(
                f"Unsupported file type: {extension or 'unknown'}.", status_code=415
            )
        
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(contents) > max_bytes:
            raise AppError(
                f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
                status_code=413,
            )
        
        try:
            raw_text = DocumentParser.parse_file(contents, filename)
        except DocumentParseError as exc:
            raise AppError(str(exc), status_code=422) from exc
        except Exception as exc:
            raise AppError("Unable to parse the uploaded document.") from exc
        if not raw_text.strip():
            raise AppError("Unable to extract text content from file.")
        return self.persist(
            db,
            filename=filename,
            file_type=extension,
            file_size=len(contents),
            raw_text=raw_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def ingest_text(
        self,
        db: Session,
        *,
        title: str,
        content: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Document:
        return self.persist(
            db,
            filename=title,
            file_type="text",
            file_size=len(content.encode("utf-8")),
            raw_text=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def persist(
        self,
        db: Session,
        *,
        filename: str,
        file_type: str,
        file_size: int,
        raw_text: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Document:
        filename = DocumentParser.sanitize_text(filename).strip()
        raw_text = DocumentParser.sanitize_text(raw_text)
        if not filename:
            raise AppError("Document filename cannot be empty.")
        if not raw_text.strip():
            raise AppError("Document content cannot be empty.")
        if chunk_overlap >= chunk_size:
            raise AppError("chunk_overlap must be smaller than chunk_size.", status_code=422)

        chunks = RecursiveChunker.split_text(raw_text, chunk_size, chunk_overlap)
        if not chunks:
            raise AppError("Content produced no indexable chunks.")

        try:
            document = Document(
                id=str(uuid.uuid4()),
                filename=filename,
                file_type=file_type,
                file_size=file_size,
            )

            embeddings = self.embedder.get_embeddings(
                [chunk["content"] for chunk in chunks]
            )
            chunk_records = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk_index = chunk["chunk_index"]
                chunk_content = chunk["content"]

                chunk_records.append(
                    {
                        "document_id": document.id,
                        "chunk_index": chunk_index,
                        "content": chunk_content,
                        "metadata": {
                            "source": filename,
                            "chunk_index": chunk_index,
                        },
                        "embedding": embedding,
                    }
                )
                
            DocumentRepository.add(db, document)
            db.flush()
            document.chunk_count = VectorStoreRepository.add_chunks(db, chunk_records)
            db.commit()
            db.refresh(document)
            return document
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_documents(db: Session) -> list[Document]:
        return DocumentRepository.list_all(db)

    @staticmethod
    def delete_document(db: Session, document_id: str) -> None:
        document = DocumentRepository.get_by_id(db, document_id)
        if not document:
            raise AppError("Document not found.", status_code=404)
        DocumentRepository.delete(db, document)
        db.commit()
