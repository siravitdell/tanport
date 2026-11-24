"""FastAPI application (REST server). Run: uvicorn app.main:app"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api import auth, health, holdings, settings
from app.config import get_settings
from app.logs import configure_logging
from app.redis_client import make_redis
from app.store.db import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = get_settings()
    configure_logging(config.log_level)
    engine = make_engine(config.database_url)
    app.state.session_factory = make_session_factory(engine)
    app.state.redis = make_redis(config.redis_url)
    structlog.get_logger().info("api.startup")
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()
        structlog.get_logger().info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="TanPort API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(holdings.router)
    app.include_router(settings.router)
    return app


app = create_app()
