"""USD/THB rates: refresh from the FX provider at most once per 24 h, read from Postgres.

Rate selection (pay date, else latest earlier rate) is the pure rule in app.domain.fx.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NoFxRateError
from app.domain.fx import FxChoice, select_rate
from app.domain.market import BANGKOK
from app.providers.base import FXProvider
from app.store import fx as fx_store

PAIR = "USD/THB"
CACHE_TTL_S = 24 * 60 * 60
REFRESH_LOOKBACK_DAYS = 14

log = structlog.get_logger()


def bangkok_today() -> date:
    return datetime.now(BANGKOK).date()


async def fx_rate_on(session: AsyncSession, on: date) -> FxChoice:
    """Read-only lookup (no provider needed): rate for `on`, else the latest earlier one."""
    found = await fx_store.latest_on_or_before(session, PAIR, on)
    if found is None:
        raise NoFxRateError(f"no {PAIR} rate stored on or before {on.isoformat()}")
    rate_date, rate = found
    return select_rate({rate_date: rate}, on)


class FxService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        provider: FXProvider,
        *,
        source: str = "bot",
        today: Callable[[], date] = bangkok_today,
    ) -> None:
        self._session = session
        self._redis = redis
        self._provider = provider
        self._source = source
        self._today = today

    @property
    def _marker(self) -> str:
        return f"fx:{PAIR}:refreshed"

    async def refresh(self, *, force: bool = False) -> int:
        """Pull the last two weeks of rates unless that already happened in the last 24 h.

        Returns the number of rates written (0 when skipped). Commits.
        """
        if not force and await self._redis.exists(self._marker):
            return 0
        end = self._today()
        rates = await self._provider.get_usd_thb(end - timedelta(days=REFRESH_LOOKBACK_DAYS), end)
        written = await fx_store.upsert_rates(self._session, rates, self._source)
        await self._session.commit()
        # Marker only after the commit: a failed write must not suppress the next attempt.
        await self._redis.set(self._marker, end.isoformat(), ex=CACHE_TTL_S)
        log.info("fx.refreshed", pair=PAIR, rates=written)
        return written

    async def backfill(self, start: date) -> int:
        """Make sure history from `start` to today is stored (e.g. old dividend pay dates).

        Only fetches the parts not already stored. Commits.
        """
        end = self._today()
        if start > end:
            return 0
        have = await fx_store.coverage(self._session, PAIR)
        ranges: list[tuple[date, date]]
        if have is None:
            ranges = [(start, end)]
        else:
            earliest, latest = have
            ranges = []
            if start < earliest:
                ranges.append((start, earliest - timedelta(days=1)))
            if latest < end:
                ranges.append((latest + timedelta(days=1), end))
        written = 0
        for range_start, range_end in ranges:
            rates = await self._provider.get_usd_thb(range_start, range_end)
            written += await fx_store.upsert_rates(self._session, rates, self._source)
        await self._session.commit()
        if written:
            log.info("fx.backfilled", pair=PAIR, rates=written, ranges=len(ranges))
        return written

    async def rate_on(self, on: date) -> FxChoice:
        """Rate for `on` (e.g. a pay date); falls back to the latest earlier rate."""
        return await fx_rate_on(self._session, on)

    async def latest(self) -> FxChoice:
        return await self.rate_on(self._today())
