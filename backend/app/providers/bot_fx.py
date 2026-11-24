"""Bank of Thailand: daily weighted-average interbank USD/THB rate.

Docs/portal: https://portal.api.bot.or.th/ (product "Exchange Rates").
Rates exist only for Thai business days; the API returns them newest first, as strings.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.domain.errors import InvalidAmountError
from app.domain.money import to_decimal
from app.providers.base import FxRate, ProviderResponseError
from app.providers.http import ProviderHttp

BASE_URL = "https://gateway.api.bot.or.th/Stat-ReferenceRate/v2/DAILY_REF_RATE/"
PAIR = "USD/THB"
# API answers 400 "Exceed limit period. Limit period is 31 days" beyond this (verified 2026-11-24).
MAX_DAYS_PER_REQUEST = 31


def _chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def parse_rates(body: Any) -> list[FxRate]:
    try:
        rows = body["result"]["data"]["data_detail"]
    except (KeyError, TypeError):
        raise ProviderResponseError("bot", "unexpected response shape") from None
    if not isinstance(rows, list):
        raise ProviderResponseError("bot", "data_detail is not a list")

    rates: list[FxRate] = []
    for row in rows:
        try:
            rate_date = date.fromisoformat(row["period"])
            rate = to_decimal(row["rate"])
        except (KeyError, TypeError, ValueError, InvalidAmountError):
            raise ProviderResponseError("bot", f"bad rate row: {row!r}") from None
        if rate <= 0:
            raise ProviderResponseError("bot", f"non-positive rate on {rate_date}")
        rates.append(FxRate(rate_date=rate_date, pair=PAIR, rate=rate))
    return rates


class BotFxProvider:
    def __init__(self, http: ProviderHttp, token: str) -> None:
        self._http = http
        self._token = token

    async def get_usd_thb(self, start: date, end: date) -> Sequence[FxRate]:
        if start > end:
            return []
        by_date: dict[date, FxRate] = {}
        for chunk_start, chunk_end in _chunks(start, end, MAX_DAYS_PER_REQUEST):
            body = await self._http.get_json(
                BASE_URL,
                params={
                    "start_period": chunk_start.isoformat(),
                    "end_period": chunk_end.isoformat(),
                },
                headers={"Authorization": self._token, "accept": "application/json"},
            )
            for rate in parse_rates(body):
                if start <= rate.rate_date <= end:
                    by_date[rate.rate_date] = rate
        return [by_date[d] for d in sorted(by_date)]
