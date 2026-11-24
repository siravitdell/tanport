from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.fx import FxChoice
from app.domain.income import DividendPayment, HoldingCost, build_income

D = Decimal
TODAY = date(2026, 11, 24)

HOLDINGS = [
    HoldingCost("KO", D("15"), D("61")),
    HoldingCost("VOO", D("2"), D("480")),
    HoldingCost("AMZN", D("3"), D("178")),  # pays nothing
    HoldingCost("SOLD", D("0"), D("10")),  # no shares → ignored
]
PAYMENTS = [
    DividendPayment("KO", date(2026, 3, 13), date(2026, 4, 1), D("0.53"), False),  # received
    DividendPayment("KO", date(2026, 12, 1), date(2026, 12, 15), D("0.53"), False),  # declared
    DividendPayment("VOO", date(2026, 12, 28), date(2026, 12, 31), D("1.85"), True),  # estimate
    DividendPayment("KO", date(2025, 12, 1), date(2025, 12, 15), D("0.51"), False),  # other year
    DividendPayment("NVDA", None, date(2026, 6, 30), D("0.01"), False),  # not held
    DividendPayment("SOLD", None, date(2026, 6, 30), D("1"), False),  # 0 shares
]
FX = {
    date(2026, 4, 1): FxChoice(D("34.0"), date(2026, 4, 1), False),
    date(2026, 12, 15): FxChoice(D("33.944"), date(2026, 11, 24), True),
    date(2026, 12, 31): FxChoice(D("33.944"), date(2026, 11, 24), True),
}


def test_payment_lines_and_months() -> None:
    inc = build_income(
        2026, today=TODAY, holdings=HOLDINGS, payments=PAYMENTS, fx=FX, withholding_rate=D("0.15")
    )
    assert len(inc.months) == 12
    april = inc.months[3]
    (line,) = april.lines
    # 15 × 0.53 = 7.95 gross; × 0.85 = 6.7575 net USD; × 34 = 229.755 THB
    assert line.amount is not None
    assert (line.amount.gross_usd, line.amount.net_usd) == (D("7.95"), D("6.7575"))
    assert line.amount.net_thb == D("229.755")
    assert line.status == "received"
    assert april.received_thb == D("229.755")
    assert april.upcoming_thb == 0

    december = inc.months[11]
    assert [(ln.ticker, ln.status, ln.is_estimate) for ln in december.lines] == [
        ("KO", "upcoming", False),  # declared, pay date still ahead
        ("VOO", "upcoming", True),
    ]
    assert december.received_thb == 0
    # KO 6.7575 × 33.944 = 229.37658 ; VOO 2 × 1.85 × 0.85 × 33.944 = 106.75388
    assert december.upcoming_thb == D("336.13046")
    assert sum(len(m.lines) for m in inc.months) == 3


def test_totals() -> None:
    inc = build_income(
        2026, today=TODAY, holdings=HOLDINGS, payments=PAYMENTS, fx=FX, withholding_rate=D("0.15")
    )
    assert inc.net_thb == D("565.88546")
    assert inc.received_thb == D("229.755")
    assert inc.upcoming_thb == D("336.13046")
    assert inc.gross_thb - inc.tax_thb == inc.net_thb
    assert inc.monthly_avg_thb == inc.net_thb / 12
    # net USD 16.66 ÷ cost (915 + 960 + 534 = 2409) × 100
    assert inc.yield_on_cost_pct is not None
    assert round(inc.yield_on_cost_pct, 4) == D("0.6916")
    assert inc.missing_fx == ()


def test_per_holding() -> None:
    inc = build_income(
        2026, today=TODAY, holdings=HOLDINGS, payments=PAYMENTS, fx=FX, withholding_rate=D("0.15")
    )
    rows = {h.ticker: h for h in inc.holdings}
    assert [h.ticker for h in inc.holdings] == ["KO", "VOO", "AMZN"]
    assert rows["KO"].pay_months == (4, 12)
    assert rows["KO"].net_usd == D("13.5150")
    assert rows["KO"].yield_on_cost_pct is not None
    assert round(rows["KO"].yield_on_cost_pct, 4) == D("1.4770")  # 13.515 / 915
    assert rows["AMZN"].pays_dividend is False
    assert rows["AMZN"].yield_on_cost_pct is None
    assert rows["AMZN"].net_thb == 0


def test_no_w8ben_rate() -> None:
    inc = build_income(
        2026,
        today=TODAY,
        holdings=HOLDINGS,
        payments=PAYMENTS[:1],
        fx=FX,
        withholding_rate=D("0.30"),
    )
    assert inc.net_thb == D("7.95") * D("0.70") * 34


def test_missing_fx_is_reported_not_zeroed() -> None:
    inc = build_income(
        2026, today=TODAY, holdings=HOLDINGS, payments=PAYMENTS, fx={}, withholding_rate=D("0.15")
    )
    assert inc.net_thb == 0
    assert inc.missing_fx == (date(2026, 4, 1), date(2026, 12, 15), date(2026, 12, 31))
    assert all(ln.amount is None for m in inc.months for ln in m.lines)
