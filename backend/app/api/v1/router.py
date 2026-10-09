from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, organizations, reference_data

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(reference_data.router)
api_router.include_router(organizations.router)
