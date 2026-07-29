from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.api_response import ApiResponse, success_response
from app.database import get_db
from app.dto import HealthResponse
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health", response_model=ApiResponse[HealthResponse])
def health_check(db: Session = Depends(get_db)):
    return success_response(HealthService.check(db))
