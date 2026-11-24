from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.moves import is_big_move


@pytest.mark.parametrize(
    ("change", "threshold", "expected"),
    [
        ("3", "3", True),  # boundary counts
        ("-3", "3", True),
        ("-5.40", "3", True),
        ("2.99", "3", False),
        ("-2.99", "3", False),
        ("0", "3", False),
        ("4", "5", False),  # configurable threshold
        (None, "3", False),  # no data is never a move
    ],
)
def test_is_big_move(change: str | None, threshold: str, expected: bool) -> None:
    value = Decimal(change) if change is not None else None
    assert is_big_move(value, Decimal(threshold)) is expected
