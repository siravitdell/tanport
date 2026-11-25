from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.trades_csv import CsvImportError, TradeRow, parse_trades_csv

D = Decimal
TODAY = date(2026, 11, 25)


def row(
    ticker: str,
    shares: str,
    price: str,
    *,
    side: str = "buy",
    day: date = TODAY,
    fee: str = "0",
    rate: str | None = None,
) -> TradeRow:
    return TradeRow(ticker, side, day, D(shares), D(price), D(fee), D(rate) if rate else None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # full trade log
        (
            "date,side,ticker,shares,price_usd,fee_usd,usd_thb\n"
            "2026-08-04,buy,VOO,1.5,585.40,0.5,33.20\n"
            "2026-11-09,sell,NVDA,2,153.87,0,32.60\n",
            [
                row("VOO", "1.5", "585.40", day=date(2026, 8, 4), fee="0.5", rate="33.20"),
                row("NVDA", "2", "153.87", side="sell", day=date(2026, 11, 9), rate="32.60"),
            ],
        ),
        # the old holdings file: each row is a buy today at the average cost, rate looked up later
        (
            "ticker,shares,avg_cost_usd\nVOO,12.5,480.20\nKO,15,61\n",
            [row("VOO", "12.5", "480.20"), row("KO", "15", "61")],
        ),
        # Excel BOM, Windows newlines, spaces, lower case, blank lines, Thai side, same ticker twice
        (
            "﻿Ticker , Shares , PRICE_USD , Side\r\n\r\n brk.b , 0.75 , 412.3 , ซื้อ \r\n"
            "BRK.B,0.25,400,ขาย\r\n",
            [row("BRK.B", "0.75", "412.3"), row("BRK.B", "0.25", "400", side="sell")],
        ),
        # extra columns are ignored; empty optional cells take their defaults
        (
            "shares,note,ticker,price_usd,date,fee_usd\n3,buy the dip,nvda,120.5,,\n",
            [row("NVDA", "3", "120.5")],
        ),
    ],
)
def test_valid_files(text: str, expected: list[TradeRow]) -> None:
    assert parse_trades_csv(text, TODAY) == expected


H = "date,side,ticker,shares,price_usd,fee_usd,usd_thb\n"


@pytest.mark.parametrize(
    ("text", "line", "column", "message"),
    [
        ("", 1, None, "file is empty"),
        ("ticker,shares\nVOO,1\n", 1, None, "missing column(s): price_usd"),
        ("ticker,price_usd\nVOO,1\n", 1, None, "missing column(s): shares"),
        (H, 2, None, "no data rows"),
        (H + "2026-11-01,buy,VOO,abc,1,0,33\n", 2, "shares", "not a number"),
        (H + "2026-11-01,buy,VOO,0,1,0,33\n", 2, "shares", "must be > 0"),
        (H + "2026-11-01,buy,VOO,1,-5,0,33\n", 2, "price_usd", "must be >= 0"),
        (H + "2026-11-01,buy,VOO,1,5,-1,33\n", 2, "fee_usd", "must be >= 0"),
        (H + "2026-11-01,buy,VOO,1,5,0,0\n", 2, "usd_thb", "must be > 0"),
        (H + "2026-11-01,buy,VOO,1e13,5,0,33\n", 2, "shares", "too large"),
        (H + "2026-11-01,buy,VOO,nan,5,0,33\n", 2, "shares", "not a number"),
        (H + "2026-11-01,buy,$VOO,1,5,0,33\n", 2, "ticker", "invalid ticker"),
        (H + "2026-11-01,hold,VOO,1,5,0,33\n", 2, "side", "must be buy or sell"),
        (H + "01/11/2026,buy,VOO,1,5,0,33\n", 2, "date", "not a YYYY-MM-DD date"),
        (H + "2026-11-26,buy,VOO,1,5,0,33\n", 2, "date", "is in the future"),
        (H + "2026-11-01,buy,VOO\n", 2, None, "expected 7 columns"),
    ],
)
def test_invalid_files(text: str, line: int, column: str | None, message: str) -> None:
    with pytest.raises(CsvImportError) as info:
        parse_trades_csv(text, TODAY)
    err = info.value.errors[0]
    assert (err.line, err.column) == (line, column)
    assert message in err.message


def test_reports_every_problem_at_once() -> None:
    text = "ticker,shares,price_usd\nVOO,x,1\nKO,1,1\n!!,-1,y\n"
    with pytest.raises(CsvImportError) as info:
        parse_trades_csv(text, TODAY)
    assert [(e.line, e.column) for e in info.value.errors] == [
        (2, "shares"),
        (4, "ticker"),
        (4, "shares"),
        (4, "price_usd"),
    ]
