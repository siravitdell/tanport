from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.earnings import announcement_time_utc, earnings_event
from app.domain.market import BANGKOK
from app.providers.base import Earnings


@pytest.mark.parametrize(
    ("report_date", "hour", "bangkok"),
    [
        # US winter (EST, UTC−5): open 09:30 = 21:30 Bangkok, close 16:00 = 04:00 next day
        (date(2027, 1, 26), "bmo", datetime(2027, 1, 26, 21, 30, tzinfo=BANGKOK)),
        (date(2027, 1, 26), "amc", datetime(2027, 1, 27, 4, 0, tzinfo=BANGKOK)),
        # US summer (EDT, UTC−4): an hour earlier in Bangkok
        (date(2026, 7, 28), "bmo", datetime(2026, 7, 28, 20, 30, tzinfo=BANGKOK)),
        (date(2026, 7, 28), "amc", datetime(2026, 7, 29, 3, 0, tzinfo=BANGKOK)),
        # early close (day after Thanksgiving 2026): 13:00 ET = 01:00 Bangkok
        (date(2026, 11, 27), "amc", datetime(2026, 11, 28, 1, 0, tzinfo=BANGKOK)),
        # no time: during market hours / unknown / not a trading day
        (date(2027, 1, 26), "dmh", None),
        (date(2027, 1, 26), "unknown", None),
        (date(2026, 12, 25), "bmo", None),  # Christmas
        (date(2026, 11, 28), "amc", None),  # Saturday
    ],
)
def test_announcement_time_in_bangkok(
    report_date: date, hour: str, bangkok: datetime | None
) -> None:
    got = announcement_time_utc(report_date, hour)
    if bangkok is None:
        assert got is None
    else:
        assert got is not None
        assert got.tzinfo is not None
        assert got == bangkok
        assert got.astimezone(UTC) == bangkok.astimezone(UTC)


def test_event_payload_keeps_figures_as_strings() -> None:
    e = Earnings(
        "NVDA",
        date(2026, 11, 17),
        "amc",
        Decimal("2.5252"),
        3,
        2027,
        eps_actual=Decimal("2.68"),
        revenue_estimate=Decimal("111294878734"),
        revenue_actual=Decimal("115844000000"),
    )
    ev = earnings_event(e)
    assert (ev.ticker, ev.event_date) == ("NVDA", date(2026, 11, 17))
    assert ev.event_time_utc == datetime(2026, 11, 17, 21, 0, tzinfo=UTC)
    assert ev.payload == {
        "hour": "amc",
        "quarter": 3,
        "fiscal_year": 2027,
        "eps_estimate": "2.5252",
        "eps_actual": "2.68",
        "revenue_estimate": "111294878734",
        "revenue_actual": "115844000000",
        "reported": True,
    }


def test_upcoming_event_is_not_reported_yet() -> None:
    ev = earnings_event(Earnings("MSFT", date(2027, 1, 26), "unknown", Decimal("4.9626"), 2, 2027))
    assert ev.event_time_utc is None
    assert ev.payload["reported"] is False
    assert ev.payload["eps_actual"] is None
