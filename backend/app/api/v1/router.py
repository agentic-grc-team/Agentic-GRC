from fastapi import APIRouter
from app.api.v1.endpoints import evidence

from app.api.v1.endpoints import health, organizations

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(organizations.router)
api_router.include_router(evidence.router, prefix="/evidence", tags=["evidence"])