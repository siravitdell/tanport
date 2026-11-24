from __future__ import annotations

import logging

import pytest

from app.logs import configure_logging


@pytest.mark.parametrize("logger", ["httpx", "httpcore"])
def test_http_client_request_logs_are_silenced(logger: str) -> None:
    """httpx logs full URLs at INFO; query strings carry API keys (Finnhub, Alpha Vantage)."""
    configure_logging("DEBUG")
    assert logging.getLogger(logger).getEffectiveLevel() >= logging.WARNING
    assert not logging.getLogger(logger).isEnabledFor(logging.INFO)
