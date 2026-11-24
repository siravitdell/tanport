"""Parse and validate a holdings CSV: `ticker,shares,avg_cost_usd`.

All-or-nothing: every row is validated first and all problems are reported together,
so a bad file never results in a partial import.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.errors import DomainError, InvalidAmountError
from app.domain.money import to_decimal

REQUIRED_COLUMNS = ("ticker", "shares", "avg_cost_usd")
MAX_ROWS = 500
MAX_AMOUNT = Decimal(10) ** 12  # fits Numeric(20, 8) / Numeric(20, 6)
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


@dataclass(frozen=True, slots=True)
class HoldingRow:
    ticker: str
    shares: Decimal
    avg_cost_usd: Decimal


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


def _parse_amount(raw: str, column: str, line: int, errors: list[RowError]) -> Decimal | None:
    try:
        value = to_decimal(raw)
    except InvalidAmountError:
        errors.append(RowError(line, column, f"not a number: {raw.strip()!r}"))
        return None
    if value < 0:
        errors.append(RowError(line, column, "must be >= 0"))
        return None
    if value >= MAX_AMOUNT:
        errors.append(RowError(line, column, f"too large (max {MAX_AMOUNT:,})"))
        return None
    return value


def parse_holdings_csv(text: str) -> list[HoldingRow]:
    text = text.removeprefix("﻿")  # Excel adds a UTF-8 BOM
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None or not any(cell.strip() for cell in header):
        raise CsvImportError([RowError(1, None, "file is empty")])

    columns = [cell.strip().lower() for cell in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise CsvImportError(
            [
                RowError(
                    1,
                    None,
                    f"missing column(s): {', '.join(missing)}; "
                    f"expected header: {','.join(REQUIRED_COLUMNS)}",
                )
            ]
        )
    index = {c: columns.index(c) for c in REQUIRED_COLUMNS}

    rows: list[HoldingRow] = []
    errors: list[RowError] = []
    seen: dict[str, int] = {}
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
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
        try:
            ticker: str | None = normalize_ticker(cells[index["ticker"]])
        except ValueError as exc:
            row_errors.append(RowError(line, "ticker", str(exc)))
            ticker = None
        shares = _parse_amount(cells[index["shares"]], "shares", line, row_errors)
        cost = _parse_amount(cells[index["avg_cost_usd"]], "avg_cost_usd", line, row_errors)

        if ticker is not None:
            if ticker in seen:
                row_errors.append(
                    RowError(line, "ticker", f"{ticker} already appears on line {seen[ticker]}")
                )
            else:
                seen[ticker] = line

        if row_errors or ticker is None or shares is None or cost is None:
            errors.extend(row_errors)
            continue
        rows.append(HoldingRow(ticker=ticker, shares=shares, avg_cost_usd=cost))

    if errors:
        raise CsvImportError(errors)
    if not rows:
        raise CsvImportError([RowError(2, None, "no data rows")])
    return rows
