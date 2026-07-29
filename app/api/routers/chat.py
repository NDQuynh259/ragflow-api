from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.api_response import ApiResponse, success_response
from app.database import get_db
from app.dto import ChatQueryRequest, ChatQueryResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/query", response_model=ApiResponse[ChatQueryResponse])
def chat_rag_query(payload: ChatQueryRequest, db: Session = Depends(get_db)):
    return success_response(ChatService().query(db, payload))
