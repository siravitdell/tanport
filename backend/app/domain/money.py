"""Decimal helpers. Never build money from a float directly; round only for display."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.errors import InvalidAmountError

type Number = Decimal | int | float | str


def to_decimal(value: Number) -> Decimal:
    """Convert provider values to Decimal. Floats go through str() to avoid binary noise."""
    if isinstance(value, bool):
        raise InvalidAmountError(f"bool is not a number: {value!r}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise InvalidAmountError(f"not a number: {value!r}") from exc
    if not result.is_finite():
        raise InvalidAmountError(f"not finite: {value!r}")
    return result


def round_display(value: Decimal, places: int = 2) -> Decimal:
    """Round half-up for display only (e.g. 0.125 -> 0.13)."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def pct_change(new: Decimal, old: Decimal) -> Decimal:
    """Percent change from old to new (1.5 means +1.5 %)."""
    if old <= 0:
        raise InvalidAmountError(f"previous value must be > 0, got {old}")
    return (new - old) / old * 100
