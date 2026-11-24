from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.fx import FxChoice
from app.domain.portfolio import Position
from app.domain.portfolio_history import DayPrice, implied_prev_close, portfolio_days

D = Decimal
D14, D15, D16 = date(2026, 12, 14), date(2026, 12, 15), date(2026, 12, 16)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (DayPrice(D("101"), D("1")), D("100")),
        (DayPrice(D("97"), D("-3")), D("100")),
        (DayPrice(D("101"), None), None),  # first day ever
        (DayPrice(D("1"), D("-100")), None),  # impossible; never divide by zero
    ],
)
def test_implied_prev_close(price: DayPrice, expected: Decimal | None) -> None:
    assert implied_prev_close(price) == expected


PRICES = {
    "VOO": {
        D14: DayPrice(D("100"), None),
        D15: DayPrice(D("102.5"), D("2.5")),
        D16: DayPrice(D("99.425"), D("-3")),
    },
    "KO": {
        D14: DayPrice(D("70"), None),
        D15: DayPrice(D("70"), D("0")),
        D16: DayPrice(D("72.1"), D("3")),
    },
}
FX = {
    D15: FxChoice(D("32.5"), D14, True),  # Thai holiday: previous day's rate
    D16: FxChoice(D("33"), D16, False),
}
POSITIONS = [Position("VOO", D("10")), Position("KO", D("20"))]


def test_daily_values() -> None:
    days = portfolio_days(POSITIONS, PRICES, FX, [D14, D15, D16])
    # 14th: no FX rate and no previous closes → no entry
    assert [d.trade_date for d in days] == [D15, D16]

    d15, d16 = days
    assert d15.change.change_usd == D("25")  # VOO 1000 → 1025, KO flat
    assert d15.fx_rate_date == D14
    assert d15.change.change_thb == D("812.5")

    # prev 1025 + 1400 = 2425 ; now 994.25 + 1442 = 2436.25
    assert d16.change.value_usd == D("2436.25")
    assert d16.change.change_usd.quantize(D("0.0001")) == D("11.25")
    assert d16.change.value_thb == D("2436.25") * 33


def test_split_does_not_distort_history() -> None:
    """After a 10:1 split the stored change % is split-adjusted, so the day is a real +1 %."""
    prices = {"NVDA": {D16: DayPrice(D("101"), D("1"))}}  # previous raw close was 1010
    (day,) = portfolio_days([Position("NVDA", D("10"))], prices, FX, [D16])
    assert day.change.change_pct == D("1")


def test_missing_price_is_excluded_not_zero() -> None:
    prices = {"VOO": PRICES["VOO"]}  # no KO data at all
    days = portfolio_days(POSITIONS, prices, FX, [D16])
    assert days[0].change.excluded == ("KO",)
    assert days[0].change.change_pct == D("-3")


@pytest.mark.parametrize("positions", [[], [Position("VOO", D("0"))]])
def test_nothing_held(positions: list[Position]) -> None:
    assert portfolio_days(positions, PRICES, FX, [D15, D16]) == []
