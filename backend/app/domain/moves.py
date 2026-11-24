"""Big-move detection: |daily change %| >= threshold becomes a `price_move` event."""

from __future__ import annotations

from decimal import Decimal

DEFAULT_BIG_MOVE_THRESHOLD_PCT = Decimal("3")


def is_big_move(
    change_pct: Decimal | None, threshold_pct: Decimal = DEFAULT_BIG_MOVE_THRESHOLD_PCT
) -> bool:
    if change_pct is None:
        return False
    return abs(change_pct) >= threshold_pct
