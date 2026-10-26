from fastapi import APIRouter

from app.api.v1.endpoints import (
    assessments,
    auth,
    evidence,
    expert_reviews,
    health,
    interviews,
    organizations,
    reference_data,
    reports,
    traces,
)


api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(reference_data.router)
api_router.include_router(organizations.router)
api_router.include_router(assessments.router)
api_router.include_router(interviews.router)
api_router.include_router(traces.router)
api_router.include_router(
    evidence.router,
    prefix="/evidence",
    tags=["evidence"],
)
api_router.include_router(expert_reviews.router)
api_router.include_router(reports.router)
