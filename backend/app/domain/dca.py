"""DCA split rules: percent per ticker, each in (0, 100], summing to exactly 100."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.domain.errors import DomainError
from app.domain.holdings_csv import normalize_ticker

HUNDRED = Decimal(100)


class InvalidDcaSplitError(DomainError, ValueError):
    pass


def validate_dca_split(split: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Return the split with normalized tickers; raise InvalidDcaSplitError when invalid."""
    if not split:
        raise InvalidDcaSplitError("DCA split must contain at least one ticker")
    out: dict[str, Decimal] = {}
    for raw_ticker, pct in split.items():
        try:
            ticker = normalize_ticker(raw_ticker)
        except ValueError as exc:
            raise InvalidDcaSplitError(str(exc)) from exc
        if ticker in out:
            raise InvalidDcaSplitError(f"{ticker} appears more than once")
        if not Decimal(0) < pct <= HUNDRED:
            raise InvalidDcaSplitError(f"{ticker}: percent must be in (0, 100], got {pct}")
        out[ticker] = pct
    total = sum(out.values(), Decimal(0))
    if total != HUNDRED:
        raise InvalidDcaSplitError(f"percentages must sum to 100, got {total}")
    return out
