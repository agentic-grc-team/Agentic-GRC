from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    application = FastAPI(
        title="Agentic GRC API",
        description="Backend API for the Agentic GRC assessment platform.",
        version="0.1.0",
    )

    cors_origins = get_settings().cors_origins
    if cors_origins:
        # The frontend sends a bearer token and never cookies, so credentials stay disabled.
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Accept", "Idempotency-Key"],
            expose_headers=["Content-Disposition"],
            max_age=600,
        )

    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
