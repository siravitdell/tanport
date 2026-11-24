from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.holdings_csv import CsvImportError, HoldingRow, parse_holdings_csv

D = Decimal


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "ticker,shares,avg_cost_usd\nVOO,12.5,480.20\nKO,15,61\n",
            [HoldingRow("VOO", D("12.5"), D("480.20")), HoldingRow("KO", D("15"), D("61"))],
        ),
        # Excel BOM, Windows newlines, spaces, lower-case ticker, blank lines
        (
            "﻿Ticker , Shares , AVG_COST_USD\r\n\r\n brk.b , 0.75 , 412.3 \r\n",
            [HoldingRow("BRK.B", D("0.75"), D("412.3"))],
        ),
        # different column order + an extra column that is ignored
        (
            "shares,note,ticker,avg_cost_usd\n3,buy the dip,nvda,120.5\n",
            [HoldingRow("NVDA", D("3"), D("120.5"))],
        ),
        # quoted values, zero shares allowed (keeps the ticker on the list)
        ('ticker,shares,avg_cost_usd\n"AMZN","0","0"\n', [HoldingRow("AMZN", D("0"), D("0"))]),
    ],
)
def test_valid_files(text: str, expected: list[HoldingRow]) -> None:
    assert parse_holdings_csv(text) == expected


@pytest.mark.parametrize(
    ("text", "line", "column", "message"),
    [
        ("", 1, None, "file is empty"),
        ("ticker,shares\nVOO,1\n", 1, None, "missing column(s): avg_cost_usd"),
        ("ticker,shares,avg_cost_usd\n", 2, None, "no data rows"),
        ("ticker,shares,avg_cost_usd\nVOO,abc,1\n", 2, "shares", "not a number"),
        ("ticker,shares,avg_cost_usd\nVOO,1,-5\n", 2, "avg_cost_usd", "must be >= 0"),
        ("ticker,shares,avg_cost_usd\nVOO,1e13,5\n", 2, "shares", "too large"),
        ("ticker,shares,avg_cost_usd\nVOO,nan,5\n", 2, "shares", "not a number"),
        ("ticker,shares,avg_cost_usd\n$VOO,1,5\n", 2, "ticker", "invalid ticker"),
        ("ticker,shares,avg_cost_usd\nVOO,1\n", 2, None, "expected 3 columns"),
        (
            "ticker,shares,avg_cost_usd\nVOO,1,5\nvoo,2,6\n",
            3,
            "ticker",
            "already appears on line 2",
        ),
    ],
)
def test_invalid_files(text: str, line: int, column: str | None, message: str) -> None:
    with pytest.raises(CsvImportError) as info:
        parse_holdings_csv(text)
    err = info.value.errors[0]
    assert (err.line, err.column) == (line, column)
    assert message in err.message


def test_reports_every_problem_at_once() -> None:
    text = "ticker,shares,avg_cost_usd\nVOO,x,1\nKO,1,1\n!!,-1,y\n"
    with pytest.raises(CsvImportError) as info:
        parse_holdings_csv(text)
    assert [(e.line, e.column) for e in info.value.errors] == [
        (2, "shares"),
        (4, "ticker"),
        (4, "shares"),
        (4, "avg_cost_usd"),
    ]
