from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.prices import with_changes
from app.providers.base import DailyBar

D = Decimal


def bar(day: int, close: str, split: str = "1") -> DailyBar:
    return DailyBar("T", date(2026, 12, day), None, None, None, D(close), D(split))


@pytest.mark.parametrize(
    ("prev", "bars", "expected"),
    [
        # first ever bar: nothing to compare with
        (None, [bar(14, "100"), bar(15, "101")], [None, D("1")]),
        # previous close comes from the database
        (D("100"), [bar(15, "97")], [D("-3")]),
        # 10:1 split: 1000 → 101 is +1 %, not −89.9 %
        (D("1000"), [bar(15, "101", split="10")], [D("1")]),
        # 1:2 reverse split (factor 0.5): 50 → 99 is −1 %
        (D("50"), [bar(15, "99", split="0.5")], [D("-1")]),
        # unsorted input is handled
        (None, [bar(16, "110"), bar(15, "100")], [None, D("10")]),
    ],
)
def test_with_changes(
    prev: Decimal | None, bars: list[DailyBar], expected: list[Decimal | None]
) -> None:
    assert [r.change_pct for r in with_changes(bars, prev)] == expected


def test_rows_keep_prices_and_dates() -> None:
    rows = with_changes([bar(15, "611.72")], D("609.95"))
    assert rows[0].trade_date == date(2026, 12, 15)
    assert rows[0].close == D("611.72")
