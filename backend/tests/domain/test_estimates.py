from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.estimates import DividendRecord, add_months, estimate_dividends

D = Decimal


def rec(ex: date, amount: str, lag_days: int | None = 15) -> DividendRecord:
    pay = ex + timedelta(days=lag_days) if lag_days is not None else None
    return DividendRecord(ex_date=ex, pay_date=pay, amount=D(amount))


KO_HISTORY = [
    rec(date(2025, 3, 14), "0.485"),
    rec(date(2025, 6, 13), "0.51"),
    rec(date(2025, 9, 15), "0.51"),
    rec(date(2025, 11, 28), "0.51"),
]


@pytest.mark.parametrize(
    ("d", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),  # leap year
        (date(2025, 12, 15), 1, date(2026, 1, 15)),
        (date(2025, 11, 30), 3, date(2026, 2, 28)),
        (date(2025, 6, 13), 12, date(2026, 6, 13)),
    ],
)
def test_add_months(d: date, months: int, expected: date) -> None:
    assert add_months(d, months) == expected


def test_quarterly_projection() -> None:
    est = estimate_dividends(KO_HISTORY, through=date(2026, 6, 30))
    # 2025-11-28 + 3m = 2026-02-28 (Saturday) → next trading day 2026-03-02; then 2026-05-28
    assert [e.ex_date for e in est] == [date(2026, 3, 2), date(2026, 5, 28)]
    assert [e.pay_date for e in est] == [date(2026, 3, 17), date(2026, 6, 12)]
    assert all(e.amount == D("0.50375") for e in est)  # mean of the last 4
    assert all(e.is_estimate for e in est)


def test_uses_only_last_four_payments() -> None:
    history = [rec(date(2024, 12, 2), "9.99"), *KO_HISTORY]
    est = estimate_dividends(history, through=date(2026, 3, 31))
    assert est[0].amount == D("0.50375")


def test_monthly_cadence() -> None:
    history = [rec(date(2026, m, 2), "0.10", lag_days=5) for m in (6, 7, 8, 9)]
    est = estimate_dividends(history, through=date(2026, 12, 31))
    assert [e.ex_date.month for e in est] == [10, 11, 12]


def test_missing_pay_dates_default_to_ex_date() -> None:
    history = [rec(e.ex_date, str(e.amount), lag_days=None) for e in KO_HISTORY]
    est = estimate_dividends(history, through=date(2026, 3, 31))
    assert est[0].pay_date == est[0].ex_date


@pytest.mark.parametrize(
    "history",
    [
        [],  # non-payer (e.g. AMZN)
        [rec(date(2025, 6, 1), "0.2")],  # one payment: cadence unknown
        [rec(date(2025, 6, 2), "0.2"), rec(date(2025, 7, 17), "0.2")],  # 45-day gap: irregular
    ],
)
def test_no_estimate(history: list[DividendRecord]) -> None:
    assert estimate_dividends(history, through=date(2027, 12, 31)) == []


def test_nothing_before_through() -> None:
    assert estimate_dividends(KO_HISTORY, through=date(2025, 12, 31)) == []
