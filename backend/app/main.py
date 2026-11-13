from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Settings are otherwise loaded lazily on first use, so /health could answer OK while an
    # invalid configuration (e.g. an insecure remote model host) is still waiting to fail.
    get_settings()
    yield


app = FastAPI(
    title="Agentic GRC API",
    description="Backend API for the Agentic GRC assessment platform.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")
