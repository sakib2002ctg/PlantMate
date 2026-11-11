"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.ai import router as ai_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.plants import router as plants_router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Configure process logging when the application starts."""

    configure_logging()
    yield


def create_app() -> FastAPI:
    """Create the application and register versioned routes and handlers."""

    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)

    @application.middleware("http")
    async def limit_ai_body_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if request.url.path.endswith(("/ai/chat", "/ai/weekly-summary")) and content_length:
            if content_length.isdigit() and int(content_length) > 8192:
                return JSONResponse(status_code=413, content={"detail": "AI request is too large"})
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_allowed_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-Device-Key"],
    )
    application.include_router(health_router)
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(dashboard_router, prefix=settings.api_v1_prefix)
    application.include_router(ingestion_router, prefix=settings.api_v1_prefix)
    application.include_router(plants_router, prefix=settings.api_v1_prefix)
    application.include_router(ai_router, prefix=settings.api_v1_prefix)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled error for %s %s", request.method, request.url.path)
        content: dict[str, Any] = {"detail": "Internal server error"}
        return JSONResponse(status_code=500, content=content)

    return application


app = create_app()
