from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.domain.portfolio import Position
from app.domain.quotes import PriceSnapshot, build_quotes_view

D = Decimal
T1 = datetime(2026, 12, 16, 20, 55, tzinfo=UTC)
T2 = datetime(2026, 12, 16, 20, 58, tzinfo=UTC)

POSITIONS = [
    Position("KO", D("20")),
    Position("VOO", D("10")),
    Position("AMZN", D("0")),  # sold out — not shown
    Position("NVDA", D("5")),  # no quote yet
]
SNAPSHOTS = {
    "VOO": PriceSnapshot(price=D("606"), prev_close=D("600"), as_of_utc=T1),  # +1 %
    "KO": PriceSnapshot(price=D("69.3"), prev_close=D("70"), as_of_utc=T2),  # −1 %
    "AMZN": PriceSnapshot(price=D("233"), prev_close=D("230"), as_of_utc=T2),
}


def test_rows_order_values_and_weights() -> None:
    view = build_quotes_view(POSITIONS, SNAPSHOTS, D("32.5"))
    assert [(h.ticker, h.status) for h in view.holdings] == [
        ("VOO", "ok"),
        ("KO", "ok"),
        ("NVDA", "no_quote"),
    ]
    voo, ko, nvda = view.holdings
    assert voo.value_usd == D("6060")
    assert voo.value_thb == D("196950.0")
    assert voo.change == D("6")
    assert voo.change_pct == D("1")
    assert ko.change_pct == D("-1")
    # current-value weights: 6060 / 7446 and 1386 / 7446
    assert voo.weight is not None
    assert ko.weight is not None
    assert abs(voo.weight + ko.weight - 1) < D("1e-20")
    assert round(voo.weight, 4) == D("0.8139")
    assert nvda.price is None
    assert nvda.weight is None


def test_portfolio_totals_use_previous_close_weights() -> None:
    view = build_quotes_view(POSITIONS, SNAPSHOTS, D("32.5"))
    p = view.portfolio
    assert p is not None
    assert p.value_usd == D("7446")
    assert p.change_usd == D("46")  # 7446 − (6000 + 1400)
    assert round(p.change_pct, 6) == D("0.621622")  # 46 / 7400
    assert p.change_thb == D("1495.0")
    assert p.excluded == ("NVDA",)


def test_as_of_is_newest_quote_among_held_tickers() -> None:
    view = build_quotes_view(POSITIONS, SNAPSHOTS, D("32.5"))
    assert view.as_of_utc == T2


def test_without_fx_rate_there_are_no_thb_values() -> None:
    view = build_quotes_view(POSITIONS, SNAPSHOTS, None)
    assert view.portfolio is None
    assert all(h.value_thb is None for h in view.holdings)
    assert view.holdings[0].value_usd == D("6060")


def test_no_quotes_at_all() -> None:
    view = build_quotes_view(POSITIONS, {}, D("32.5"))
    assert [h.status for h in view.holdings] == ["no_quote"] * 3
    assert view.portfolio is None
    assert view.as_of_utc is None


def test_empty_portfolio() -> None:
    view = build_quotes_view([], SNAPSHOTS, D("32.5"))
    assert view.holdings == ()
    assert view.portfolio is None
