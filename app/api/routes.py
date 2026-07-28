import uuid
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    DocumentResponse,
    HealthResponse,
    IngestTextRequest,
    SearchQueryRequest,
    SearchQueryResponse,
    SearchResultChunk,
)
from app.config import settings
from app.database import get_db
from app.models import Document
from app.services.chunker import TextChunker
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.parser import DocumentParseError, DocumentParser
from app.services.prompt_builder import PromptBuilder
from app.services.vector_store import VectorStoreService

router = APIRouter()


def _validate_chunk_window(chunk_size: int, chunk_overlap: int) -> None:
    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chunk_overlap must be smaller than chunk_size.",
        )


def _persist_document(
    db: Session,
    *,
    filename: str,
    file_type: str,
    file_size: int,
    raw_text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> Document:
    """Persist a document and all chunks in one database transaction."""
    filename = DocumentParser.sanitize_text(filename).strip()
    raw_text = DocumentParser.sanitize_text(raw_text)
    if not filename:
        raise HTTPException(status_code=400, detail="Document filename cannot be empty.")
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Document content cannot be empty.")

    raw_chunks = TextChunker.split_text(
        raw_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not raw_chunks:
        raise HTTPException(status_code=400, detail="Content produced no indexable chunks.")

    try:
        doc = Document(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            file_size=file_size,
        )

        embedder = EmbeddingService()
        chunks_to_insert = []
        for chunk in raw_chunks:
            chunks_to_insert.append({
                "document_id": doc.id,
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "metadata": {
                    "source": filename,
                    "chunk_index": chunk["chunk_index"],
                },
                "embedding": embedder.get_embedding(chunk["content"]),
            })

        db.add(doc)
        db.flush()
        doc.chunk_count = VectorStoreService.add_chunks(db, chunks_to_insert)
        db.commit()
        db.refresh(doc)
        return doc
    except Exception:
        db.rollback()
        raise


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Check both the database connection and the pgvector extension."""
    db_connected = False
    pgvector_active = False
    schema_ready = False
    try:
        db_connected = db.execute(text("SELECT 1")).scalar() == 1
        pgvector_active = (
            db.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            ).scalar()
            == "vector"
        )
        schema_ready = bool(
            db.execute(text("""
                SELECT
                    to_regclass('public.documents') IS NOT NULL
                    AND to_regclass('public.document_chunks') IS NOT NULL
                    AND to_regclass('public.alembic_version') IS NOT NULL;
            """)).scalar()
        )
    except Exception:
        pass

    return HealthResponse(
        status=(
            "healthy"
            if db_connected and pgvector_active and schema_ready
            else "unhealthy"
        ),
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        database_connected=db_connected,
        pgvector_extension=pgvector_active,
        schema_ready=schema_ready,
        embedding_provider=settings.EMBEDDING_PROVIDER,
        llm_provider=settings.LLM_PROVIDER,
    )


@router.post(
    "/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: UploadFile = File(...),
    chunk_size: int = Form(settings.DEFAULT_CHUNK_SIZE, gt=0, le=10000),
    chunk_overlap: int = Form(settings.DEFAULT_CHUNK_OVERLAP, ge=0),
    db: Session = Depends(get_db),
):
    """Upload, parse, chunk, embed, and store a supported document."""
    _validate_chunk_window(chunk_size, chunk_overlap)

    filename = DocumentParser.sanitize_text(file.filename or "upload.txt").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Document filename cannot be empty.")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in settings.ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {extension or 'unknown'}.",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    contents = file.file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
        )

    try:
        raw_text = DocumentParser.parse_file(contents, filename)
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to parse the uploaded document.",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Unable to extract text content from file.")

    return _persist_document(
        db,
        filename=filename,
        file_type=extension,
        file_size=len(contents),
        raw_text=raw_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


@router.post(
    "/documents/ingest-text",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_text(payload: IngestTextRequest, db: Session = Depends(get_db)):
    """Ingest raw text directly into the RAG pipeline."""
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")

    return _persist_document(
        db,
        filename=payload.title,
        file_type="text",
        file_size=len(payload.content.encode("utf-8")),
        raw_text=payload.content,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )


@router.get("/documents", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    """List all ingested documents."""
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """Delete a document and all associated chunks."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    db.delete(doc)
    db.commit()
    return {"status": "success", "message": f"Document {doc_id} deleted successfully."}


@router.post("/retrieval/search", response_model=SearchQueryResponse)
def search_retrieval(payload: SearchQueryRequest, db: Session = Depends(get_db)):
    """Execute vector or hybrid retrieval against PostgreSQL."""
    query_vector = EmbeddingService().get_embedding(payload.query)

    if payload.search_type == "vector":
        results = VectorStoreService.search_vector(
            db,
            query_vector=query_vector,
            top_k=payload.top_k,
            document_id=payload.document_id,
        )
    else:
        results = VectorStoreService.search_hybrid(
            db,
            query_text=payload.query,
            query_vector=query_vector,
            top_k=payload.top_k,
            document_id=payload.document_id,
        )

    return SearchQueryResponse(
        query=payload.query,
        top_k=payload.top_k,
        search_type=payload.search_type,
        results=[SearchResultChunk(**result) for result in results],
    )


@router.post("/chat/query", response_model=ChatQueryResponse)
def chat_rag_query(payload: ChatQueryRequest, db: Session = Depends(get_db)):
    """Run the end-to-end retrieval-augmented generation pipeline."""
    query_vector = EmbeddingService().get_embedding(payload.query)

    if payload.search_type == "vector":
        contexts = VectorStoreService.search_vector(
            db,
            query_vector=query_vector,
            top_k=payload.top_k,
            document_id=payload.document_id,
        )
    else:
        contexts = VectorStoreService.search_hybrid(
            db,
            query_text=payload.query,
            query_vector=query_vector,
            top_k=payload.top_k,
            document_id=payload.document_id,
        )

    full_prompt = PromptBuilder.build_rag_prompt(
        query=payload.query,
        contexts=contexts,
        system_instruction=payload.system_instruction,
    )
    answer = LLMService().generate_response(full_prompt)

    return ChatQueryResponse(
        query=payload.query,
        answer=answer,
        retrieved_contexts=[SearchResultChunk(**context) for context in contexts],
    )
