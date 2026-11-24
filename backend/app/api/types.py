"""Shared API field types. Money/ratios are Decimal in Python and strings in JSON."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def decimal_to_str(value: Decimal) -> str:
    """Plain notation without trailing zeros: Decimal('12.50000000') -> '12.5'."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


# Accepts a JSON string ("12.5") or number; always serialized as a string.
DecimalStr = Annotated[Decimal, PlainSerializer(decimal_to_str, return_type=str, when_used="json")]
