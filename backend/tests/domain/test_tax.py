from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import InvalidAmountError
from app.domain.tax import dividend_amount, net_dividend_thb

D = Decimal


@pytest.mark.parametrize(
    ("shares", "dps", "rate", "fx", "expected_thb"),
    [
        # 10 × 0.51 × 0.85 × 32.50
        ("10", "0.51", "0.15", "32.50", "140.887500"),
        # no W-8BEN → 30 %
        ("10", "0.51", "0.30", "32.50", "116.025000"),
        # fractional shares
        ("2.5", "1.7742", "0.15", "33.1234", "124.88"),
        # holding with 0 shares, or a non-payer
        ("0", "0.51", "0.15", "32.50", "0"),
        ("10", "0", "0.15", "32.50", "0"),
    ],
)
def test_net_dividend_thb(shares: str, dps: str, rate: str, fx: str, expected_thb: str) -> None:
    result = net_dividend_thb(D(shares), D(dps), D(rate), D(fx))
    assert result.quantize(D("0.01")) == D(expected_thb).quantize(D("0.01"))


def test_breakdown_adds_up() -> None:
    a = dividend_amount(D("10"), D("0.51"), D("0.15"), D("32.50"))
    assert a.gross_usd == D("5.10")
    assert a.tax_usd == D("0.7650")
    assert a.net_usd == D("4.3350")
    assert a.gross_thb - a.tax_thb == a.net_thb
    assert a.usd_thb == D("32.50")


@pytest.mark.parametrize(
    ("shares", "dps", "rate", "fx"),
    [
        ("-1", "0.5", "0.15", "32"),
        ("1", "-0.5", "0.15", "32"),
        ("1", "0.5", "-0.01", "32"),
        ("1", "0.5", "1.01", "32"),
        ("1", "0.5", "0.15", "0"),
    ],
)
def test_rejects_invalid_inputs(shares: str, dps: str, rate: str, fx: str) -> None:
    with pytest.raises(InvalidAmountError):
        dividend_amount(D(shares), D(dps), D(rate), D(fx))
