from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.api_response import ApiResponse, success_response
from app.storage.database.postgres import get_db
from app.api.schemas.document import DocumentResponse
from app.ingestion.pipeline import IngestionPipeline
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
    document = IngestionPipeline().ingest_pdf(
        db,
        filename=file.filename or "upload.pdf",
        contents=file.file.read(max_bytes + 1),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return success_response(document, message="Document uploaded successfully.")


# region list_documents
@router.get("", response_model=ApiResponse[list[DocumentResponse]])
def list_documents(db: Session = Depends(get_db)):
    return success_response(IngestionPipeline.list_documents(db))

# region delete_document
@router.delete("/{document_id}", response_model=ApiResponse[None])
def delete_document(document_id: str, db: Session = Depends(get_db)):
    IngestionPipeline.delete_document(db, document_id)
    return success_response(message=f"Document {document_id} deleted successfully.")
