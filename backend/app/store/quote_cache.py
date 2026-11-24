"""Latest quotes live in Redis only (not Postgres). One JSON value per ticker.

Kept for a week so weekend/holiday views still show the last session's prices.
Decimals are stored as strings.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from redis.asyncio import Redis

from app.providers.base import Quote

TTL_S = 7 * 24 * 60 * 60


def _key(ticker: str) -> str:
    return f"quote:{ticker}"


def _dump(q: Quote) -> str:
    return json.dumps(
        {
            "ticker": q.ticker,
            "price": str(q.price),
            "prev_close": str(q.prev_close),
            "change": str(q.change),
            "change_pct": str(q.change_pct),
            "as_of_utc": q.as_of_utc.isoformat(),
        }
    )


def _load(raw: str | bytes) -> Quote:
    d = json.loads(raw)
    return Quote(
        ticker=d["ticker"],
        price=Decimal(d["price"]),
        prev_close=Decimal(d["prev_close"]),
        change=Decimal(d["change"]),
        change_pct=Decimal(d["change_pct"]),
        as_of_utc=datetime.fromisoformat(d["as_of_utc"]),
    )


async def save_quote(redis: Redis, quote: Quote) -> None:
    await redis.set(_key(quote.ticker), _dump(quote), ex=TTL_S)


async def load_quotes(redis: Redis, tickers: Iterable[str]) -> dict[str, Quote]:
    tickers = list(tickers)
    if not tickers:
        return {}
    raws = await redis.mget([_key(t) for t in tickers])
    return {t: _load(raw) for t, raw in zip(tickers, raws, strict=True) if raw is not None}
