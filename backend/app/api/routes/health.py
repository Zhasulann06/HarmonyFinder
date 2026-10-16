"""Service health endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.core.config import settings


class HealthResponse(BaseModel):
    """Health endpoint response payload."""

    status: str
    service: str


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report whether the API process is available."""
    return HealthResponse(status="ok", service=settings.service_name)

