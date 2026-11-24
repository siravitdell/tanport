from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import InvalidAmountError
from app.domain.money import Number, pct_change, round_display, to_decimal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.1, Decimal("0.1")),  # Decimal(0.1) would be 0.1000000000000000055511...
        (611.72, Decimal("611.72")),
        (1.1 + 2.2, Decimal("3.3000000000000003")),  # str() keeps what the float really is
        (5, Decimal("5")),
        (" 12.50 ", Decimal("12.50")),
        (Decimal("1.23"), Decimal("1.23")),
    ],
)
def test_to_decimal(value: Number, expected: Decimal) -> None:
    assert to_decimal(value) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "abc", "", True])
def test_to_decimal_rejects_non_numbers(value: Number) -> None:
    with pytest.raises(InvalidAmountError):
        to_decimal(value)


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        (Decimal("0.125"), 2, Decimal("0.13")),
        (Decimal("0.135"), 2, Decimal("0.14")),
        (Decimal("-0.125"), 2, Decimal("-0.13")),
        (Decimal("140.8875"), 2, Decimal("140.89")),
        (Decimal("533.5"), 0, Decimal("534")),
    ],
)
def test_round_display_half_up(value: Decimal, places: int, expected: Decimal) -> None:
    assert round_display(value, places) == expected


@pytest.mark.parametrize(
    ("new", "old", "expected"),
    [
        ("101", "100", "1"),
        ("95", "100", "-5"),
        ("100", "100", "0"),
    ],
)
def test_pct_change(new: str, old: str, expected: str) -> None:
    assert pct_change(Decimal(new), Decimal(old)) == Decimal(expected)


@pytest.mark.parametrize("old", ["0", "-1"])
def test_pct_change_requires_positive_base(old: str) -> None:
    with pytest.raises(InvalidAmountError):
        pct_change(Decimal("1"), Decimal(old))
