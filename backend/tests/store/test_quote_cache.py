from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from redis.asyncio import Redis

from app.providers.base import Quote
from app.store.quote_cache import TTL_S, load_quotes, save_quote

QUOTE = Quote(
    ticker="VOO",
    price=Decimal("611.72"),
    prev_close=Decimal("609.95"),
    change=Decimal("1.77"),
    change_pct=Decimal("0.2901877203049430281170587753"),
    as_of_utc=datetime(2026, 12, 16, 20, 59, tzinfo=UTC),
)


async def test_roundtrip_keeps_exact_decimals(redis: Redis) -> None:
    await save_quote(redis, QUOTE)
    assert await load_quotes(redis, ["VOO"]) == {"VOO": QUOTE}


async def test_missing_tickers_are_absent(redis: Redis) -> None:
    await save_quote(redis, QUOTE)
    assert set(await load_quotes(redis, ["VOO", "KO"])) == {"VOO"}
    assert await load_quotes(redis, []) == {}


async def test_quotes_expire_after_a_week(redis: Redis) -> None:
    await save_quote(redis, QUOTE)
    assert TTL_S - 5 < await redis.ttl("quote:VOO") <= TTL_S
