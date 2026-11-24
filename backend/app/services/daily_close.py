"""Daily closes → prices, price_move events, and every user's portfolio_daily.

Per ticker: fetch from the last stored day minus a week (picks up late corrections), or
BACKFILL_DAYS for a new ticker. Portfolio history is then recomputed for the last
BACKFILL_DAYS for all users, so someone who just imported holdings gets history too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NoFxRateError
from app.domain.fx import FxChoice
from app.domain.moves import is_big_move
from app.domain.portfolio_history import portfolio_days
from app.domain.prices import PriceRow, with_changes
from app.providers.base import PriceHistoryProvider
from app.services.fx import fx_rate_on
from app.store import portfolio_daily as portfolio_store
from app.store import prices as price_store
from app.store.events import EventIn, delete_events, upsert_events
from app.store.holdings import positions_by_user
from app.store.models import EventType

BACKFILL_DAYS = 100  # calendar days ≈ 68 trading days: a couple of calendar months + sparklines
OVERLAP_DAYS = 7
PCT_PLACES = Decimal("0.000001")

log = structlog.get_logger()


@dataclass
class DailyCloseResult:
    saved: dict[str, int] = field(default_factory=dict)  # ticker -> rows written
    failed: dict[str, str] = field(default_factory=dict)
    moves: int = 0
    portfolio_days: int = 0


class DailyCloseService:
    def __init__(
        self, session: AsyncSession, provider: PriceHistoryProvider, *, source: str = "tiingo"
    ) -> None:
        self._session = session
        self._provider = provider
        self._source = source

    async def sync_ticker(self, ticker: str, end: date) -> tuple[date, list[PriceRow]]:
        """Fetch and store closes for one ticker. Returns (range start, rows written)."""
        last = await price_store.last_trade_date(self._session, ticker)
        start = last - timedelta(days=OVERLAP_DAYS) if last else end - timedelta(days=BACKFILL_DAYS)
        bars = await self._provider.get_daily_bars(ticker, start, end)
        if not bars:
            return start, []
        first = min(b.trade_date for b in bars)
        prev_close = await price_store.close_before(self._session, ticker, first)
        rows = with_changes(bars, prev_close)
        await price_store.upsert_prices(self._session, rows, self._source)
        return start, rows

    async def record_moves(
        self, ticker: str, start: date, end: date, rows: list[PriceRow], threshold: Decimal
    ) -> int:
        """Re-derive price_move events for the range (removes ones that no longer qualify)."""
        await delete_events(
            self._session,
            event_type=EventType.PRICE_MOVE,
            ticker=ticker,
            start=start,
            end=end,
            source=self._source,
        )
        events = [
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker=ticker,
                event_date=r.trade_date,
                source=self._source,
                # same precision as prices.change_pct (Numeric 12,6)
                payload={"change_pct": str(_db_pct(r.change_pct)), "close": str(r.close)},
            )
            for r in rows
            if r.change_pct is not None and is_big_move(r.change_pct, threshold)
        ]
        await upsert_events(self._session, events)
        return len(events)

    async def recompute_portfolios(self, end: date) -> int:
        start = end - timedelta(days=BACKFILL_DAYS)
        by_user = await positions_by_user(self._session)
        tickers = {p.ticker for positions in by_user.values() for p in positions}
        prices = await price_store.day_prices(self._session, tickers, start, end)
        dates = {d for per_ticker in prices.values() for d in per_ticker}

        fx: dict[date, FxChoice] = {}
        for d in dates:
            try:
                fx[d] = await fx_rate_on(self._session, d)
            except NoFxRateError:
                log.warning("portfolio.no_fx_rate", trade_date=d.isoformat())

        written = 0
        for user_id, positions in by_user.items():
            days = portfolio_days(positions, prices, fx, dates)
            written += await portfolio_store.replace_days(self._session, user_id, start, end, days)
        return written


def _db_pct(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(PCT_PLACES, rounding=ROUND_HALF_UP)
