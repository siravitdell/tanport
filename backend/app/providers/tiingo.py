"""Tiingo end-of-day prices (free "Starter" tier: 50 req/h, 1000 req/day; stocks + ETFs)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.domain.errors import InvalidAmountError
from app.domain.money import to_decimal
from app.providers.base import DailyBar, ProviderResponseError
from app.providers.http import ProviderHttp

BASE_URL = "https://api.tiingo.com/tiingo/daily"


def _optional(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    return None if value is None else to_decimal(value)


def parse_bars(ticker: str, body: Any) -> list[DailyBar]:
    if not isinstance(body, list):
        raise ProviderResponseError("tiingo", f"prices for {ticker}: expected a list")
    bars: list[DailyBar] = []
    for row in body:
        try:
            # "2026-11-23T00:00:00.000Z" is the US trading date, not a UTC instant.
            trade_date = date.fromisoformat(str(row["date"])[:10])
            close = to_decimal(row["close"])
            split = row.get("splitFactor")
            bars.append(
                DailyBar(
                    ticker=ticker,
                    trade_date=trade_date,
                    open=_optional(row, "open"),
                    high=_optional(row, "high"),
                    low=_optional(row, "low"),
                    close=close,
                    split_factor=to_decimal(split) if split is not None else to_decimal(1),
                )
            )
        except (KeyError, TypeError, ValueError, InvalidAmountError):
            raise ProviderResponseError("tiingo", f"prices for {ticker}: bad row") from None
        if close <= 0 or bars[-1].split_factor <= 0:
            raise ProviderResponseError("tiingo", f"prices for {ticker}: non-positive value")
    bars.sort(key=lambda b: b.trade_date)
    return bars


class TiingoPriceProvider:
    def __init__(self, http: ProviderHttp, token: str) -> None:
        self._http = http
        self._token = token

    async def get_daily_bars(self, ticker: str, start: date, end: date) -> Sequence[DailyBar]:
        if start > end:
            return []
        body = await self._http.get_json(
            f"{BASE_URL}/{ticker}/prices",
            params={"startDate": start.isoformat(), "endDate": end.isoformat()},
            # Token in a header keeps it out of URLs (and therefore out of any proxy logs).
            headers={"Authorization": f"Token {self._token}"},
        )
        return [b for b in parse_bars(ticker, body) if start <= b.trade_date <= end]
