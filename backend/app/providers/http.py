"""Shared HTTP plumbing for providers: rate limiting, retries, error mapping.

Never put a request URL in an error or log message: API keys travel in query strings.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
import structlog

from app.providers.base import (
    ProviderAccessDeniedError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.ratelimit import RateLimiter, RateLimitExceededError

log = structlog.get_logger()

Sleep = Callable[[float], Awaitable[None]]


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class ProviderHttp:
    def __init__(
        self,
        provider: str,
        client: httpx.AsyncClient,
        limiter: RateLimiter | None = None,
        *,
        limiter_max_wait_s: float = 60,
        retries: int = 2,
        backoff_s: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self._client = client
        self._limiter = limiter
        self._limiter_max_wait_s = limiter_max_wait_s
        self._retries = retries
        self._backoff_s = backoff_s
        self._sleep = sleep

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        path = httpx.URL(url).path
        last_problem = "no attempt made"
        for attempt in range(self._retries + 1):
            if attempt:
                await self._sleep(self._backoff_s * 2 ** (attempt - 1))
            if self._limiter is not None:
                try:
                    await self._limiter.acquire(max_wait_s=self._limiter_max_wait_s)
                except RateLimitExceededError as exc:
                    raise ProviderRateLimitedError(
                        self.provider, "local rate limit reached", exc.retry_after_s
                    ) from None

            try:
                resp = await self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                last_problem = type(exc).__name__
                log.warning(
                    "provider.transport_error",
                    provider=self.provider,
                    path=path,
                    error=last_problem,
                    attempt=attempt,
                )
                continue

            status = resp.status_code
            if status in (401, 403):
                raise ProviderAccessDeniedError(self.provider, f"HTTP {status} on {path}")
            if status == 429:
                raise ProviderRateLimitedError(
                    self.provider, f"HTTP 429 on {path}", _retry_after(resp)
                )
            if status >= 500:
                last_problem = f"HTTP {status}"
                log.warning(
                    "provider.server_error",
                    provider=self.provider,
                    path=path,
                    status=status,
                    attempt=attempt,
                )
                continue
            if status >= 400:
                raise ProviderResponseError(self.provider, f"HTTP {status} on {path}")
            try:
                return resp.json()
            except ValueError:
                raise ProviderResponseError(self.provider, f"invalid JSON from {path}") from None

        raise ProviderUnavailableError(
            self.provider, f"{path} failed after {self._retries + 1} attempts ({last_problem})"
        )
