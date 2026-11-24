"""Shared resources for jobs (worker and one-off CLI runs): DB, Redis, HTTP, providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.providers.base import ProviderError
from app.providers.bot_fx import BotFxProvider
from app.providers.http import ProviderHttp
from app.ratelimit import provider_limiter
from app.redis_client import make_redis
from app.store.db import make_engine, make_session_factory

HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ProviderNotConfiguredError(ProviderError):
    """The API key/token for a provider is missing from the environment."""


@dataclass(frozen=True)
class Runtime:
    config: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient

    def bot_fx(self) -> BotFxProvider:
        token = self.config.bot_api_token.get_secret_value()
        if not token:
            raise ProviderNotConfiguredError("bot", "BOT_API_TOKEN is not set")
        http = ProviderHttp("bot", self.http, provider_limiter(self.redis, "bot"))
        return BotFxProvider(http, token)


@asynccontextmanager
async def open_runtime(config: Settings | None = None) -> AsyncIterator[Runtime]:
    config = config or get_settings()
    engine = make_engine(config.database_url)
    redis = make_redis(config.redis_url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
        try:
            yield Runtime(
                config=config,
                session_factory=make_session_factory(engine),
                redis=redis,
                http=http,
            )
        finally:
            await redis.aclose()
            await engine.dispose()
