"""Health check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.api_response import ApiResponse, success_response
from app.storage.database.postgres import get_db
from app.api.schemas.health import HealthResponse
from app.api.routes.health_service import HealthService

router = APIRouter()

@router.get("/health", response_model=ApiResponse[HealthResponse])
def health_check(db: Session = Depends(get_db)):
    return success_response(HealthService.check(db))
