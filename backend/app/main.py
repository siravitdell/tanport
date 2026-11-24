"""FastAPI application (REST server). Run: uvicorn app.main:app"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api import health
from app.config import get_settings
from app.logs import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    structlog.get_logger().info("api.startup")
    yield
    structlog.get_logger().info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="TanPort API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
