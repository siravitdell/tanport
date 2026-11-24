from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.portfolio import HoldingDay, portfolio_change, weights

D = Decimal
FX = D("32.50")


def h(ticker: str, shares: str, prev: str | None, close: str | None) -> HoldingDay:
    return HoldingDay(
        ticker=ticker,
        shares=D(shares),
        prev_close=D(prev) if prev is not None else None,
        close=D(close) if close is not None else None,
    )


@pytest.mark.parametrize(
    ("days", "change_pct", "change_usd"),
    [
        # equal weights: 0.5 × +1 % + 0.5 × −5 % = −2 %
        ([h("A", "10", "100", "101"), h("B", "5", "200", "190")], "-2", "-40"),
        # 75/25 weights: 0.75 × +2 % + 0.25 × −4 % = +0.5 %
        ([h("A", "30", "100", "102"), h("B", "10", "100", "96")], "0.5", "20"),
        # single holding
        ([h("NVDA", "3", "152.95", "144.71")], "-5.387381", "-24.72"),
        # flat day is a real 0 %
        ([h("A", "1", "50", "50")], "0", "0"),
    ],
)
def test_weighted_change(days: list[HoldingDay], change_pct: str, change_usd: str) -> None:
    result = portfolio_change(days, FX)
    assert result is not None
    assert result.change_pct.quantize(D("0.000001")) == D(change_pct).quantize(D("0.000001"))
    assert result.change_usd == D(change_usd)
    assert result.change_thb == D(change_usd) * FX
    assert result.value_thb == result.value_usd * FX


def test_weighted_sum_equals_value_change() -> None:
    days = [
        h("A", "7", "611.72", "613.50"),
        h("B", "12.5", "28.73", "28.81"),
        h("C", "4", "70", "69"),
    ]
    r = portfolio_change(days, FX)
    assert r is not None
    direct = (r.value_usd - r.prev_value_usd) / r.prev_value_usd * 100
    assert abs(r.change_pct - direct) < D("1e-20")
    assert sum(c.weight for c in r.holdings) == pytest.approx(D(1))


def test_missing_prices_are_excluded_not_zero() -> None:
    r = portfolio_change(
        [h("A", "10", "100", "101"), h("NEW", "5", None, "10"), h("HALT", "5", "10", None)], FX
    )
    assert r is not None
    assert r.excluded == ("NEW", "HALT")
    assert [c.ticker for c in r.holdings] == ["A"]
    assert r.change_pct == D(1)


def test_zero_share_holdings_are_ignored() -> None:
    r = portfolio_change([h("A", "10", "100", "101"), h("AMZN", "0", "230", "233")], FX)
    assert r is not None
    assert [c.ticker for c in r.holdings] == ["A"]
    assert r.excluded == ()


@pytest.mark.parametrize(
    "days",
    [[], [h("A", "0", "1", "1")], [h("A", "1", None, None)]],
)
def test_nothing_priceable_returns_none(days: list[HoldingDay]) -> None:
    assert portfolio_change(days, FX) is None


def test_holdings_sorted_by_abs_change() -> None:
    r = portfolio_change(
        [h("S", "1", "100", "100.5"), h("BIG", "1", "100", "94.6"), h("MID", "1", "100", "101.9")],
        FX,
    )
    assert r is not None
    assert [c.ticker for c in r.holdings] == ["BIG", "MID", "S"]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"A": D("75"), "B": D("25")}, {"A": D("0.75"), "B": D("0.25")}),
        ({"A": D("0"), "B": D("0")}, {"A": D("0"), "B": D("0")}),
        ({}, {}),
    ],
)
def test_weights(values: dict[str, Decimal], expected: dict[str, Decimal]) -> None:
    assert weights(values) == expected
