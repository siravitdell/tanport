from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_money_settings_are_decimal() -> None:
    settings = Settings(_env_file=None, withholding_rate="0.30")
    assert settings.withholding_rate == Decimal("0.30")
    assert isinstance(settings.big_move_threshold_pct, Decimal)


@pytest.mark.parametrize("rate", ["-0.01", "1.5"])
def test_withholding_rate_must_be_between_0_and_1(rate: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, withholding_rate=rate)
