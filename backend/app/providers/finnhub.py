"""Finnhub (free tier): latest quotes.

Candles and dividends are premium-only on Finnhub (see docs/data-sources.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.errors import InvalidAmountError
from app.domain.money import pct_change, to_decimal
from app.providers.base import ProviderResponseError, Quote
from app.providers.http import ProviderHttp

BASE_URL = "https://finnhub.io/api/v1"


def parse_quote(ticker: str, body: Any) -> Quote:
    if not isinstance(body, dict):
        raise ProviderResponseError("finnhub", f"quote for {ticker}: not an object")
    try:
        price = to_decimal(body["c"])
        prev_close = to_decimal(body["pc"])
        timestamp = int(body["t"])
    except (KeyError, TypeError, ValueError, InvalidAmountError):
        raise ProviderResponseError("finnhub", f"quote for {ticker}: bad fields") from None
    # Unknown symbols come back as all zeros instead of an error.
    if price <= 0 or prev_close <= 0 or timestamp <= 0:
        raise ProviderResponseError("finnhub", f"no quote data for {ticker}")
    return Quote(
        ticker=ticker,
        price=price,
        prev_close=prev_close,
        change=price - prev_close,
        change_pct=pct_change(price, prev_close),
        as_of_utc=datetime.fromtimestamp(timestamp, UTC),
    )


class FinnhubQuoteProvider:
    def __init__(self, http: ProviderHttp, token: str) -> None:
        self._http = http
        self._token = token

    async def get_quote(self, ticker: str) -> Quote:
        body = await self._http.get_json(
            f"{BASE_URL}/quote", params={"symbol": ticker, "token": self._token}
        )
        return parse_quote(ticker, body)
