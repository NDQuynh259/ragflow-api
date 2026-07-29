from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.api_response import ApiResponse, success_response
from app.database import get_db
from app.dto import SearchQueryRequest, SearchQueryResponse
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.post("/search", response_model=ApiResponse[SearchQueryResponse])
def search_retrieval(payload: SearchQueryRequest, db: Session = Depends(get_db)):
    return success_response(RetrievalService().search(db, payload))
