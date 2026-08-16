"""Document ingestion use cases."""

import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.domain.document import Document
from app.storage.database.repositories.document import DocumentRepository
from app.storage.vector.pgvector import VectorStoreRepository
from app.ingestion.chunkers.semantic import SemanticChunker
from app.embeddings.base import EmbeddingService
from app.ingestion.parsers.layout_parser import (
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    LayoutBlock,
    LayoutParseError,
    LayoutParser,
)


class IngestionPipeline:
    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        self.embedder = embedder or EmbeddingService()

    def ingest_pdf(
        self,
        db: Session,
        *,
        filename: str,
        contents: bytes,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Document:
        filename = self._sanitize_text(filename or "upload.pdf").strip()
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
        
        """Ingest a PDF as layout-aware text, table, and image nodes.

        Each block becomes a document node; vector retrieval reads these nodes
        directly rather than a separate legacy chunk table.
        """
        if chunk_overlap >= chunk_size:
            raise AppError("chunk_overlap must be smaller than chunk_size.", status_code=422)

        try:
            blocks = LayoutParser().parse_pdf(contents)
        except LayoutParseError as exc:
            raise AppError(str(exc), status_code=422) from exc
        except Exception as exc:
            raise AppError("Unable to parse the uploaded PDF.") from exc
        if not blocks:
            raise AppError("Unable to extract text, table, or image content from PDF.")

        document = Document(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type="pdf",
            file_size=len(contents),
        )
        try:
            node_records = self._build_layout_records(
                document_id=document.id,
                filename=filename,
                blocks=blocks,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            if not node_records:
                raise AppError("PDF produced no indexable layout nodes.")

            embeddable_nodes = [record for record in node_records if record["content"].strip()]
            embeddings = self.embedder.get_embeddings(
                [record["content"] for record in embeddable_nodes]
            )
            for record, embedding in zip(embeddable_nodes, embeddings, strict=True):
                record["embedding"] = embedding

            DocumentRepository.add(db, document)
            db.flush()
            VectorStoreRepository.add_nodes(db, node_records)
            document.chunk_count = len(node_records)
            db.commit()
            db.refresh(document)
            return document
        except Exception:
            db.rollback()
            raise

    @classmethod
    def _build_layout_records(
        cls,
        *,
        document_id: str,
        filename: str,
        blocks: list[LayoutBlock],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict]:
        """Route layout blocks into retrievable multimodal nodes."""
        node_records: list[dict] = []
        node_index = 0
        semantic_chunker = SemanticChunker()

        for block in blocks:
            metadata = {
                "source": filename,
                "page_number": block.page_number,
                "bbox": list(block.bbox),
                **block.metadata,
            }
            if block.block_type == BLOCK_TYPE_TEXT:
                for chunk in semantic_chunker.split(block.text, chunk_size, chunk_overlap):
                    record = cls._build_text_node(
                        document_id=document_id,
                        node_index=node_index,
                        chunk=chunk,
                        metadata=metadata,
                    )
                    if record:
                        node_records.append(record)
                        node_index += 1
            elif block.block_type == BLOCK_TYPE_TABLE:
                record = cls._build_table_node(
                    document_id=document_id,
                    node_index=node_index,
                    block=block,
                    metadata=metadata,
                )
                if record:
                    node_records.append(record)
                    node_index += 1
            elif block.block_type == BLOCK_TYPE_IMAGE:
                node_records.append(
                    cls._build_image_node(
                        document_id=document_id,
                        node_index=node_index,
                        block=block,
                        metadata=metadata,
                    )
                )
                node_index += 1

        return node_records

    @staticmethod
    def _build_text_node(
        *, document_id: str, node_index: int, chunk: dict, metadata: dict
    ) -> dict | None:
        """Create a text node from one semantic text chunk."""
        content = IngestionPipeline._sanitize_text(chunk["content"]).strip()
        if not content:
            return None
        return {
            "document_id": document_id,
            "node_type": BLOCK_TYPE_TEXT,
            "node_index": node_index,
            "content": content,
            "metadata": {**metadata, "semantic_chunk_index": chunk["chunk_index"]},
        }

    @staticmethod
    def _build_table_node(
        *, document_id: str, node_index: int, block: LayoutBlock, metadata: dict
    ) -> dict | None:
        """Create a table node with Markdown content and structured row data."""
        content = IngestionPipeline._sanitize_text(block.text).strip()
        if not content:
            return None
        return {
            "document_id": document_id,
            "node_type": BLOCK_TYPE_TABLE,
            "node_index": node_index,
            "content": content,
            "structured_data": {"rows": block.rows or []},
            "metadata": metadata,
        }

    @staticmethod
    def _build_image_node(
        *, document_id: str, node_index: int, block: LayoutBlock, metadata: dict
    ) -> dict:
        """Create an image node for the later classify/vision pipeline stage."""
        return {
            "document_id": document_id,
            "node_type": BLOCK_TYPE_IMAGE,
            "node_index": node_index,
            "content": "",
            "metadata": {**metadata, "image_name": block.image_name},
        }

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

    @staticmethod
    def _sanitize_text(text: str | None) -> str:
        """Normalize text through the PDF layout parser's safe text contract."""
        return LayoutParser.sanitize_text(text)
