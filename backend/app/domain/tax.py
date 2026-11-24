"""Dividend tax: net THB = shares × dps × (1 − withholding_rate) × usd_thb."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.errors import InvalidAmountError

DEFAULT_WITHHOLDING_RATE = Decimal("0.15")  # US–Thailand treaty with W-8BEN
NO_W8BEN_WITHHOLDING_RATE = Decimal("0.30")


@dataclass(frozen=True, slots=True)
class DividendAmount:
    gross_usd: Decimal
    tax_usd: Decimal
    net_usd: Decimal
    usd_thb: Decimal
    gross_thb: Decimal
    tax_thb: Decimal
    net_thb: Decimal


def dividend_amount(
    shares: Decimal, dps_usd: Decimal, withholding_rate: Decimal, usd_thb: Decimal
) -> DividendAmount:
    if shares < 0:
        raise InvalidAmountError(f"shares must be >= 0, got {shares}")
    if dps_usd < 0:
        raise InvalidAmountError(f"dividend per share must be >= 0, got {dps_usd}")
    if not Decimal(0) <= withholding_rate <= Decimal(1):
        raise InvalidAmountError(f"withholding rate must be in [0, 1], got {withholding_rate}")
    if usd_thb <= 0:
        raise InvalidAmountError(f"FX rate must be > 0, got {usd_thb}")

    gross_usd = shares * dps_usd
    tax_usd = gross_usd * withholding_rate
    net_usd = gross_usd - tax_usd
    return DividendAmount(
        gross_usd=gross_usd,
        tax_usd=tax_usd,
        net_usd=net_usd,
        usd_thb=usd_thb,
        gross_thb=gross_usd * usd_thb,
        tax_thb=tax_usd * usd_thb,
        net_thb=net_usd * usd_thb,
    )


def net_dividend_thb(
    shares: Decimal, dps_usd: Decimal, withholding_rate: Decimal, usd_thb: Decimal
) -> Decimal:
    return dividend_amount(shares, dps_usd, withholding_rate, usd_thb).net_thb
