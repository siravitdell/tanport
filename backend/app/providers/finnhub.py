"""Finnhub (free tier): latest quotes, earnings calendar.

Candles and dividends are premium-only on Finnhub (see docs/data-sources.md). The earnings
calendar is asked per symbol: the whole-market list is capped at 1,500 rows and comes back
truncated.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.domain.errors import InvalidAmountError
from app.domain.money import pct_change, to_decimal
from app.providers.base import Earnings, EarningsHour, ProviderResponseError, Quote
from app.providers.http import ProviderHttp

HOURS: dict[str, EarningsHour] = {"bmo": "bmo", "amc": "amc", "dmh": "dmh"}

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


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return to_decimal(value)
    except InvalidAmountError:
        return None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_earnings(ticker: str, body: Any) -> list[Earnings]:
    """`{"earningsCalendar": [...]}` → rows for `ticker` only (bad rows are skipped)."""
    if not isinstance(body, dict) or not isinstance(body.get("earningsCalendar"), list):
        raise ProviderResponseError("finnhub", f"earnings for {ticker}: unexpected shape")
    out: list[Earnings] = []
    for row in body["earningsCalendar"]:
        if not isinstance(row, dict) or row.get("symbol") != ticker:
            continue
        try:
            report_date = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        out.append(
            Earnings(
                ticker=ticker,
                report_date=report_date,
                hour=HOURS.get(str(row.get("hour") or "").lower(), "unknown"),
                eps_estimate=_amount(row.get("epsEstimate")),
                quarter=_int(row.get("quarter")),
                year=_int(row.get("year")),
                eps_actual=_amount(row.get("epsActual")),
                revenue_estimate=_amount(row.get("revenueEstimate")),
                revenue_actual=_amount(row.get("revenueActual")),
            )
        )
    return sorted(out, key=lambda e: e.report_date)


class FinnhubEarningsProvider:
    def __init__(self, http: ProviderHttp, token: str) -> None:
        self._http = http
        self._token = token

    async def get_earnings(self, ticker: str, start: date, end: date) -> Sequence[Earnings]:
        body = await self._http.get_json(
            f"{BASE_URL}/calendar/earnings",
            params={
                "symbol": ticker,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": self._token,
            },
        )
        return parse_earnings(ticker, body)


class FinnhubQuoteProvider:
    def __init__(self, http: ProviderHttp, token: str) -> None:
        self._http = http
        self._token = token

    async def get_quote(self, ticker: str) -> Quote:
        body = await self._http.get_json(
            f"{BASE_URL}/quote", params={"symbol": ticker, "token": self._token}
        )
        return parse_quote(ticker, body)
