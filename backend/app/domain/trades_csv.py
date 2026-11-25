"""Parse and validate a trades CSV.

Columns (header names, any order):
  required  ticker, shares, price_usd   (avg_cost_usd is accepted for price_usd, so an old
                                         `ticker,shares,avg_cost_usd` holdings file still works)
  optional  date (YYYY-MM-DD, default today), side (buy/sell or ซื้อ/ขาย, default buy),
            fee_usd (default 0), usd_thb (default: the Bank of Thailand rate of that date)

All-or-nothing: every row is validated first and all problems are reported together,
so a bad file never results in a partial import.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.errors import DomainError, InvalidAmountError
from app.domain.money import to_decimal

MAX_ROWS = 500
MAX_AMOUNT = Decimal(10) ** 12  # fits Numeric(20, 8) / Numeric(20, 6)
MAX_RATE = Decimal(10) ** 6  # fits Numeric(12, 6)
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")
PRICE_ALIASES = ("price_usd", "avg_cost_usd")
SIDES = {"buy": "buy", "sell": "sell", "ซื้อ": "buy", "ขาย": "sell", "b": "buy", "s": "sell"}


@dataclass(frozen=True, slots=True)
class TradeRow:
    ticker: str
    side: str
    trade_date: date
    shares: Decimal
    price_usd: Decimal
    fee_usd: Decimal
    usd_thb: Decimal | None  # None: look up the rate of trade_date
    line: int = field(default=0, compare=False)  # where it came from, for error messages


@dataclass(frozen=True, slots=True)
class RowError:
    line: int  # 1-based line number in the file (header = line 1)
    column: str | None
    message: str


class CsvImportError(DomainError):
    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(f"{len(errors)} problem(s) in CSV")
        self.errors = errors


def normalize_ticker(raw: str) -> str:
    """Upper-case and validate a ticker; raises ValueError when invalid."""
    ticker = raw.strip().upper()
    if not TICKER_RE.match(ticker):
        raise ValueError(f"invalid ticker {raw.strip()!r}")
    return ticker


def _amount(
    raw: str,
    column: str,
    line: int,
    errors: list[RowError],
    *,
    positive: bool = False,
    limit: Decimal = MAX_AMOUNT,
) -> Decimal | None:
    try:
        value = to_decimal(raw)
    except InvalidAmountError:
        errors.append(RowError(line, column, f"not a number: {raw.strip()!r}"))
        return None
    if value < 0 or (positive and value == 0):
        errors.append(RowError(line, column, "must be > 0" if positive else "must be >= 0"))
        return None
    if value >= limit:
        errors.append(RowError(line, column, f"too large (max {limit:,})"))
        return None
    return value


def parse_trades_csv(text: str, today: date) -> list[TradeRow]:
    text = text.removeprefix("﻿")  # Excel adds a UTF-8 BOM
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None or not any(cell.strip() for cell in header):
        raise CsvImportError([RowError(1, None, "file is empty")])

    columns = [cell.strip().lower() for cell in header]
    price_col = next((c for c in PRICE_ALIASES if c in columns), None)
    missing = [c for c in ("ticker", "shares") if c not in columns]
    if price_col is None:
        missing.append("price_usd")
    if missing:
        raise CsvImportError(
            [
                RowError(
                    1,
                    None,
                    f"missing column(s): {', '.join(missing)}; expected header: "
                    "date,side,ticker,shares,price_usd,fee_usd,usd_thb "
                    "(date, side, fee_usd and usd_thb are optional)",
                )
            ]
        )
    assert price_col is not None  # reported as missing above otherwise
    col = {c: i for i, c in enumerate(columns)}

    def cell(cells: list[str], name: str) -> str:
        i = col.get(name)
        return cells[i].strip() if i is not None and i < len(cells) else ""

    rows: list[TradeRow] = []
    errors: list[RowError] = []
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue  # blank line
        if len(rows) + len(errors) >= MAX_ROWS:
            errors.append(RowError(line, None, f"too many rows (max {MAX_ROWS})"))
            break
        if len(cells) < len(columns):
            errors.append(
                RowError(line, None, f"expected {len(columns)} columns, got {len(cells)}")
            )
            continue

        row_errors: list[RowError] = []
        ticker: str | None
        try:
            ticker = normalize_ticker(cell(cells, "ticker"))
        except ValueError as exc:
            row_errors.append(RowError(line, "ticker", str(exc)))
            ticker = None

        side = SIDES.get(cell(cells, "side").lower() or "buy")
        if side is None:
            row_errors.append(RowError(line, "side", "must be buy or sell"))

        trade_date: date | None = today
        if raw_date := cell(cells, "date"):
            try:
                trade_date = date.fromisoformat(raw_date)
            except ValueError:
                row_errors.append(RowError(line, "date", f"not a YYYY-MM-DD date: {raw_date!r}"))
                trade_date = None
            else:
                if trade_date > today:
                    row_errors.append(RowError(line, "date", "is in the future"))
                    trade_date = None

        shares = _amount(cell(cells, "shares"), "shares", line, row_errors, positive=True)
        price = _amount(cell(cells, price_col), price_col, line, row_errors)
        raw_fee = cell(cells, "fee_usd")
        fee = _amount(raw_fee, "fee_usd", line, row_errors) if raw_fee else Decimal(0)
        raw_rate = cell(cells, "usd_thb")
        rate = (
            _amount(raw_rate, "usd_thb", line, row_errors, positive=True, limit=MAX_RATE)
            if raw_rate
            else None
        )

        if (
            row_errors
            or ticker is None
            or side is None
            or trade_date is None
            or shares is None
            or price is None
            or fee is None
            or (raw_rate and rate is None)
        ):
            errors.extend(row_errors)
            continue
        rows.append(TradeRow(ticker, side, trade_date, shares, price, fee, rate, line))

    if errors:
        raise CsvImportError(errors)
    if not rows:
        raise CsvImportError([RowError(2, None, "no data rows")])
    return rows
