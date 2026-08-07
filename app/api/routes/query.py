"""Query & Chat RAG routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.api_response import ApiResponse, success_response
from app.storage.database.postgres import get_db
from app.api.schemas.query import (
    SearchQueryRequest, SearchQueryResponse,
    ChatQueryRequest, ChatQueryResponse,
)
from app.retrieval.pipeline import RetrievalPipeline
from app.generation.generator import RAGGenerator

router = APIRouter()

@router.post("/search", response_model=ApiResponse[SearchQueryResponse])
def search_retrieval(payload: SearchQueryRequest, db: Session = Depends(get_db)):
    return success_response(RetrievalPipeline().search(db, payload))

@router.post("/query", response_model=ApiResponse[ChatQueryResponse])
def chat_rag_query(payload: ChatQueryRequest, db: Session = Depends(get_db)):
    return success_response(RAGGenerator().generate(db, payload))
