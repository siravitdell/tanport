from __future__ import annotations


class DomainError(Exception):
    """Base class for business-rule violations."""


class InvalidAmountError(DomainError, ValueError):
    """A money/quantity value is not a finite number or is out of range."""


class NoFxRateError(DomainError, LookupError):
    """No FX rate is available on or before the requested date."""
