"""FX rate selection: use the rate of the target date, else the latest rate before it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.errors import NoFxRateError


@dataclass(frozen=True, slots=True)
class FxChoice:
    rate: Decimal
    rate_date: date  # which day's rate was used — shown in the UI
    is_fallback: bool  # True when rate_date != requested date


def select_rate(rates: Mapping[date, Decimal], on: date) -> FxChoice:
    """Pick the FX rate for `on` (e.g. a dividend pay date).

    Falls back to the most recent rate before `on` (weekends, Thai holidays, or a
    future pay date). Never uses a rate from after `on`.
    """
    exact = rates.get(on)
    if exact is not None:
        return FxChoice(rate=exact, rate_date=on, is_fallback=False)
    earlier = [d for d in rates if d < on]
    if not earlier:
        raise NoFxRateError(f"no FX rate on or before {on.isoformat()}")
    latest = max(earlier)
    return FxChoice(rate=rates[latest], rate_date=latest, is_fallback=True)
