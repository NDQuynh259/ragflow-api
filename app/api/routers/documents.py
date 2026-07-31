from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.api_response import ApiResponse, success_response
from app.database import get_db
from app.dto import DocumentResponse, IngestTextRequest
from app.services.document_service import DocumentService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
# region upload_document
@router.post("/upload", response_model=ApiResponse[DocumentResponse], status_code=status.HTTP_201_CREATED)
def upload_document(
    file: Annotated[UploadFile, File(...)],
    chunk_size: Annotated[int, Form(gt=0, le=10000)] = settings.DEFAULT_CHUNK_SIZE,
    chunk_overlap: Annotated[int, Form(ge=0)] = settings.DEFAULT_CHUNK_OVERLAP,
    db: Session = Depends(get_db),
):
    
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    document = DocumentService().ingest_file(
        db,
        filename=file.filename or "upload.txt",
        contents=file.file.read(max_bytes + 1),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return success_response(document, message="Document uploaded successfully.")


# region ingest_text
@router.post("/ingest-text", response_model=ApiResponse[DocumentResponse], status_code=status.HTTP_201_CREATED)
def ingest_text(payload: IngestTextRequest, db: Session = Depends(get_db)):
    document = DocumentService().ingest_text(
        db,
        title=payload.title,
        content=payload.content,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )
    return success_response(document, message="Text ingested successfully.")


# region list_documents
@router.get("", response_model=ApiResponse[list[DocumentResponse]])
def list_documents(db: Session = Depends(get_db)):
    return success_response(DocumentService.list_documents(db))

# region delete_document
@router.delete("/{document_id}", response_model=ApiResponse[None])
def delete_document(document_id: str, db: Session = Depends(get_db)):
    DocumentService.delete_document(db, document_id)
    return success_response(message=f"Document {document_id} deleted successfully.")
