from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.dca import InvalidDcaSplitError, validate_dca_split

D = Decimal


@pytest.mark.parametrize(
    ("split", "expected"),
    [
        (
            {"VOO": D(70), "QQQM": D(20), "SCHD": D(10)},
            {"VOO": D(70), "QQQM": D(20), "SCHD": D(10)},
        ),
        ({"voo": D(100)}, {"VOO": D(100)}),
        ({"A": D("33.33"), "B": D("33.33"), "C": D("33.34")}, None),
    ],
)
def test_valid_split(split: dict[str, Decimal], expected: dict[str, Decimal] | None) -> None:
    result = validate_dca_split(split)
    assert result == (expected if expected is not None else split)


@pytest.mark.parametrize(
    ("split", "message"),
    [
        ({}, "at least one"),
        ({"VOO": D(70), "QQQM": D(20)}, "sum to 100, got 90"),
        ({"VOO": D(100), "KO": D(0)}, "must be in (0, 100]"),
        ({"VOO": D(110), "KO": D(-10)}, "must be in (0, 100]"),
        ({"VOO": D(50), "voo": D(50)}, "more than once"),
        ({"V O O": D(100)}, "invalid ticker"),
    ],
)
def test_invalid_split(split: dict[str, Decimal], message: str) -> None:
    with pytest.raises(InvalidDcaSplitError) as info:
        validate_dca_split(split)
    assert message in str(info.value)
