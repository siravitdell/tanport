from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import NoFxRateError
from app.domain.fx import select_rate

RATES = {
    date(2026, 12, 1): Decimal("32.50"),
    date(2026, 12, 3): Decimal("32.70"),
}


@pytest.mark.parametrize(
    ("on", "rate", "rate_date", "fallback"),
    [
        (date(2026, 12, 3), "32.70", date(2026, 12, 3), False),  # exact pay-date rate
        (date(2026, 12, 2), "32.50", date(2026, 12, 1), True),  # gap (holiday) → day before
        (date(2026, 12, 10), "32.70", date(2026, 12, 3), True),  # future pay date → latest
    ],
)
def test_select_rate(on: date, rate: str, rate_date: date, fallback: bool) -> None:
    choice = select_rate(RATES, on)
    assert choice.rate == Decimal(rate)
    assert choice.rate_date == rate_date
    assert choice.is_fallback is fallback


@pytest.mark.parametrize(
    "rates",
    [{}, {date(2026, 12, 5): Decimal("33")}],  # never use a rate from after the date
)
def test_no_rate_on_or_before(rates: dict[date, Decimal]) -> None:
    with pytest.raises(NoFxRateError):
        select_rate(rates, date(2026, 12, 1))
