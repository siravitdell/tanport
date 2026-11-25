from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.trades import Book, OversellError, TradeFact, portfolio_view, replay

D = Decimal


def buy(
    day: int,
    shares: str,
    price: str,
    rate: str,
    fee: str = "0",
    t: str = "VOO",
    id_: int | None = None,
) -> TradeFact:
    return TradeFact(t, "buy", date(2026, 11, day), D(shares), D(price), D(fee), D(rate), id_)


def sell(
    day: int,
    shares: str,
    price: str,
    rate: str,
    fee: str = "0",
    t: str = "VOO",
    id_: int | None = None,
) -> TradeFact:
    return TradeFact(t, "sell", date(2026, 11, day), D(shares), D(price), D(fee), D(rate), id_)


def test_buy_cost_includes_fee_in_both_currencies() -> None:
    book = replay([buy(1, "10", "100", "35", fee="1")])["VOO"]
    assert (book.shares, book.cost_usd, book.cost_thb) == (D(10), D(1001), D(35035))
    assert book.avg_cost_usd == D("100.1")
    assert book.trades == 1


def test_average_cost_and_partial_sell() -> None:
    trades = [
        buy(1, "10", "100", "35"),
        buy(2, "10", "120", "34"),
        sell(3, "5", "130", "33", fee="1"),
    ]
    book = replay(trades)["VOO"]
    # 20 shares cost $2,200 / ฿75,800; a quarter of that leaves with the sale
    assert book.shares == D(15)
    assert book.cost_usd == D(1650)
    assert book.avg_cost_usd == D(110)  # unchanged by a sale
    assert book.cost_thb == D(56850)
    # proceeds $649 (5 × 130 − 1) − basis $550
    assert book.realized_usd == D(99)
    # ฿21,417 (649 × 33) − basis ฿18,950
    assert book.realized_thb == D(2467)


def test_closing_a_position_keeps_realized_and_clears_cost() -> None:
    book = replay([buy(1, "3", "10", "30"), sell(2, "1", "12", "30"), sell(3, "2", "9", "31")])[
        "VOO"
    ]
    assert book.shares == 0
    assert (book.cost_usd, book.cost_thb) == (D(0), D(0))
    assert book.avg_cost_usd is None
    assert book.realized_usd == D(2) + D(-2)  # +2 then −2
    assert book.realized_thb == D(60) + (D(18) * 31 - D(600))  # 360 − 300, then 558 − 600


def test_fractional_shares() -> None:
    book = replay([buy(1, "0.8125", "598.20", "32.5"), sell(2, "0.3125", "600", "32.5")])["VOO"]
    assert book.shares == D("0.5")
    assert book.avg_cost_usd == D("598.20")


@pytest.mark.parametrize(
    "trades",
    [
        [sell(1, "1", "10", "30")],  # nothing held
        [buy(1, "1", "10", "30"), sell(2, "1.00000001", "10", "30")],
        [sell(1, "1", "10", "30"), buy(2, "1", "10", "30")],  # sold before it was bought
        [buy(1, "2", "10", "30", t="KO"), sell(2, "1", "10", "30", t="VOO")],  # other ticker
    ],
)
def test_oversell_is_rejected(trades: list[TradeFact]) -> None:
    with pytest.raises(OversellError, match="cannot sell"):
        replay(trades)


def test_same_day_buys_count_before_sells_whatever_the_entry_order() -> None:
    book = replay([sell(5, "1", "11", "30", id_=1), buy(5, "1", "10", "30", id_=2)])["VOO"]
    assert book.shares == 0
    assert book.realized_usd == D(1)


def test_tickers_are_independent() -> None:
    books = replay([buy(1, "1", "10", "30", t="KO"), buy(1, "2", "20", "30", t="V")])
    assert {t: b.shares for t, b in books.items()} == {"KO": D(1), "V": D(2)}


# --- portfolio view ---


def two_buys() -> dict[str, Book]:
    return replay([buy(1, "10", "100", "35"), buy(2, "10", "120", "34")])  # $2,200 / ฿75,800


def test_unrealized_splits_into_price_and_fx() -> None:
    view = portfolio_view(two_buys(), {"VOO": D(130)}, D(33))
    [row] = view.positions
    assert row.value_usd == D(2600)
    assert row.value_thb == D(85800)
    assert row.unrealized_thb == D(10000)
    assert row.price_pl_thb == D(13200)  # (2600 − 2200) × 33
    assert row.fx_pl_thb == D(-3200)  # 2200 × 33 − 75800: the baht got stronger
    assert row.price_pl_thb + row.fx_pl_thb == row.unrealized_thb
    assert row.weight_pct == D(100)
    assert view.totals is not None
    assert view.totals.unrealized_thb == D(10000)
    assert view.totals.trades == 2


def test_unpriced_positions_are_listed_but_left_out_of_value_and_pl() -> None:
    books = replay([buy(1, "10", "100", "35"), buy(1, "4", "50", "35", t="NEW")])
    view = portfolio_view(books, {"VOO": D(110)}, D(35))
    assert [r.ticker for r in view.positions] == ["VOO", "NEW"]  # priced first, by value
    new = view.positions[1]
    assert (new.value_usd, new.unrealized_thb, new.weight_pct) == (None, None, None)
    assert view.totals is not None
    assert view.totals.value_usd == D(1100)
    assert view.totals.cost_usd == D(1200)  # every open position
    assert view.totals.unrealized_thb == D(3500)  # VOO only
    assert view.totals.unpriced == ("NEW",)


def test_weights_and_realized_from_closed_positions() -> None:
    books = replay(
        [
            buy(1, "1", "300", "30", t="A"),
            buy(1, "1", "100", "30", t="B"),
            buy(1, "1", "10", "30", t="GONE"),
            sell(2, "1", "15", "30", t="GONE"),
        ]
    )
    view = portfolio_view(books, {"A": D(300), "B": D(100)}, D(30))
    assert [(r.ticker, r.weight_pct) for r in view.positions] == [("A", D(75)), ("B", D(25))]
    assert view.totals is not None
    assert view.totals.realized_usd == D(5)
    assert view.totals.realized_thb == D(150)
    assert view.totals.trades == 4


def test_no_trades_no_totals() -> None:
    assert portfolio_view({}, {}, D(33)).totals is None
