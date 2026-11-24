from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.domain.dividends import ESTIMATE_SOURCE, dividend_events
from app.providers.alphavantage import parse_dividends
from app.providers.base import Dividend

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "alphavantage"
START, THROUGH = date(2025, 1, 1), date(2027, 12, 31)


def ko() -> list[Dividend]:
    body = json.loads((FIXTURES / "dividends_KO.json").read_text(encoding="utf-8"))
    return parse_dividends("KO", body)


def test_ex_and_pay_are_separate_events() -> None:
    events = dividend_events("KO", ko(), window_start=START, through=THROUGH, source="alphavantage")
    dec = [e for e in events if not e.is_estimate and e.payload["ex_date"] == "2026-12-01"]
    assert [(e.type, e.event_date) for e in dec] == [
        ("ex_dividend", date(2026, 12, 1)),
        ("dividend_pay", date(2026, 12, 15)),
    ]
    assert dec[0].payload == {
        "dps": "0.53",
        "ex_date": "2026-12-01",
        "pay_date": "2026-12-15",
        "record_date": "2026-12-01",
        "declaration_date": "2026-10-15",
    }
    assert all(e.source == "alphavantage" for e in dec)


def test_estimates_follow_the_last_declared_payment() -> None:
    events = dividend_events("KO", ko(), window_start=START, through=THROUGH, source="alphavantage")
    estimates = [e for e in events if e.is_estimate]
    assert estimates
    assert all(e.source == ESTIMATE_SOURCE for e in estimates)
    ex_dates = [e.event_date for e in estimates if e.type == "ex_dividend"]
    assert min(ex_dates) > date(2026, 12, 1)
    assert max(ex_dates) <= THROUGH
    assert len(ex_dates) == 4  # quarterly through 2027
    assert {e.payload["dps"] for e in estimates} == {"0.530000"}  # mean of the last four


def test_window_bounds() -> None:
    events = dividend_events(
        "KO", ko(), window_start=date(2026, 6, 1), through=date(2026, 12, 31), source="av"
    )
    assert all(date(2026, 6, 1) <= e.event_date <= date(2026, 12, 31) for e in events)
    # the pay date of a payment whose ex-date is before the window is still included
    assert ("dividend_pay", date(2026, 7, 1)) in [(e.type, e.event_date) for e in events]


def test_non_payer_has_no_events() -> None:
    assert dividend_events("AMZN", [], window_start=START, through=THROUGH, source="av") == []
