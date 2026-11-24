"""Alpha Vantage DIVIDENDS (free: 25 requests/day). Paid + declared dividends with pay dates.

Quirks (see docs/data-sources.md):
- amounts are strings; dates may be the string "None"
- rows with amount 0 exist (AMZN 2022-12-27) and are dropped
- throttling/quota errors come back as HTTP 200 with an "Information" or "Note" key,
  both for the 25/day quota and for the 1 request/second burst limit
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.domain.errors import InvalidAmountError
from app.domain.money import to_decimal
from app.providers.base import (
    Dividend,
    ProviderRateLimitedError,
    ProviderResponseError,
)
from app.providers.http import ProviderHttp

BASE_URL = "https://www.alphavantage.co/query"
BURST_RETRY_S = 2.0


def _date(value: Any) -> date | None:
    if value in (None, "", "None"):
        return None
    return date.fromisoformat(str(value))


def parse_dividends(ticker: str, body: Any) -> list[Dividend]:
    if not isinstance(body, dict):
        raise ProviderResponseError("alphavantage", f"dividends for {ticker}: not an object")
    for key in ("Information", "Note"):
        if key in body:
            message = str(body[key])
            # Two different limits share this shape (verified 2026-11-24):
            #   "... 25 requests per day ..."            → quota gone until tomorrow
            #   "... 1 request per second ..." (burst)   → fine again in a moment
            daily = "per day" in message.lower()
            raise ProviderRateLimitedError(
                "alphavantage", message[:200], None if daily else BURST_RETRY_S
            )
    if "Error Message" in body:
        raise ProviderResponseError("alphavantage", str(body["Error Message"])[:200])
    rows = body.get("data")
    if not isinstance(rows, list):
        raise ProviderResponseError("alphavantage", f"dividends for {ticker}: no data list")

    bad_row = ProviderResponseError("alphavantage", f"dividends for {ticker}: bad row")
    out: list[Dividend] = []
    for row in rows:
        try:
            ex_date = _date(row["ex_dividend_date"])
            amount = to_decimal(row["amount"])
            pay_date = _date(row.get("payment_date"))
            record_date = _date(row.get("record_date"))
            declaration_date = _date(row.get("declaration_date"))
        except (KeyError, TypeError, ValueError, InvalidAmountError):
            raise bad_row from None
        if ex_date is None or amount < 0:
            raise bad_row
        if amount == 0:
            continue  # placeholder rows, e.g. AMZN, which pays no dividend
        out.append(
            Dividend(
                ticker=ticker,
                ex_date=ex_date,
                pay_date=pay_date,
                record_date=record_date,
                declaration_date=declaration_date,
                amount=amount,
            )
        )
    out.sort(key=lambda d: d.ex_date)
    return out


class AlphaVantageDividendProvider:
    def __init__(self, http: ProviderHttp, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def get_dividends(self, ticker: str) -> Sequence[Dividend]:
        body = await self._http.get_json(
            BASE_URL, params={"function": "DIVIDENDS", "symbol": ticker, "apikey": self._api_key}
        )
        return parse_dividends(ticker, body)
