# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""Probe which market-data endpoints our API keys can actually use.

Usage (from repo root):  uv run backend/scripts/probe_providers.py

Reads keys from ./.env. Writes raw response bodies to
backend/scripts/probe_output/ (gitignored) and prints a summary table.
API keys are sent in query/header only and are never written to disk.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "probe_output"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    params: dict[str, str]
    headers: dict[str, str]
    key_name: str


def build_probes(env: dict[str, str]) -> list[Probe]:
    today = date.today()
    d30 = today - timedelta(days=30)
    y2 = today - timedelta(days=730)

    def unix(d: date) -> str:
        return str(int(datetime.combine(d, time(), tzinfo=UTC).timestamp()))

    fh = env.get("FINNHUB_API_KEY", "")
    ti = env.get("TIINGO_API_KEY", "")
    av = env.get("ALPHAVANTAGE_API_KEY", "")
    bot = env.get("BOT_API_TOKEN", "")
    fh_base = "https://finnhub.io/api/v1"

    return [
        Probe("finnhub_quote_VOO", f"{fh_base}/quote", {"symbol": "VOO", "token": fh}, {}, "FINNHUB_API_KEY"),
        Probe(
            "finnhub_candle_VOO",
            f"{fh_base}/stock/candle",
            {"symbol": "VOO", "resolution": "D", "from": unix(d30), "to": unix(today), "token": fh},
            {},
            "FINNHUB_API_KEY",
        ),
        Probe(
            "finnhub_dividend_KO",
            f"{fh_base}/stock/dividend",
            {"symbol": "KO", "from": y2.isoformat(), "to": today.isoformat(), "token": fh},
            {},
            "FINNHUB_API_KEY",
        ),
        Probe("finnhub_dividend2_KO", f"{fh_base}/stock/dividend2", {"symbol": "KO", "token": fh}, {}, "FINNHUB_API_KEY"),
        Probe(
            "finnhub_earnings_cal",
            f"{fh_base}/calendar/earnings",
            {"from": today.isoformat(), "to": (today + timedelta(days=90)).isoformat(), "symbol": "MSFT", "token": fh},
            {},
            "FINNHUB_API_KEY",
        ),
        Probe(
            "finnhub_economic_cal",
            f"{fh_base}/calendar/economic",
            {"from": today.isoformat(), "to": (today + timedelta(days=30)).isoformat(), "token": fh},
            {},
            "FINNHUB_API_KEY",
        ),
        Probe(
            "tiingo_eod_VOO",
            "https://api.tiingo.com/tiingo/daily/VOO/prices",
            {"startDate": d30.isoformat(), "token": ti},
            {},
            "TIINGO_API_KEY",
        ),
        Probe(
            "tiingo_eod_KO_divcash",
            "https://api.tiingo.com/tiingo/daily/KO/prices",
            {"startDate": y2.isoformat(), "token": ti},
            {},
            "TIINGO_API_KEY",
        ),
        Probe(
            "tiingo_distributions_KO",
            "https://api.tiingo.com/tiingo/corporate-actions/KO/distributions",
            {"token": ti},
            {},
            "TIINGO_API_KEY",
        ),
        Probe(
            "alphavantage_dividends_KO",
            "https://www.alphavantage.co/query",
            {"function": "DIVIDENDS", "symbol": "KO", "apikey": av},
            {},
            "ALPHAVANTAGE_API_KEY",
        ),
        Probe(
            "alphavantage_dividends_AMZN",
            "https://www.alphavantage.co/query",
            {"function": "DIVIDENDS", "symbol": "AMZN", "apikey": av},
            {},
            "ALPHAVANTAGE_API_KEY",
        ),
        Probe(
            "bot_daily_ref_rate",
            "https://gateway.api.bot.or.th/Stat-ReferenceRate/v2/DAILY_REF_RATE/",
            {"start_period": d30.isoformat(), "end_period": today.isoformat()},
            {"Authorization": bot, "accept": "application/json"},
            "BOT_API_TOKEN",
        ),
    ]


def verdict(status: int, body: str) -> str:
    low = body.lower()
    if status in (401, 403) or "don't have access" in low or "premium" in low:
        return "BLOCKED"
    if status == 429 or "rate limit" in low or "call frequency" in low:
        return "RATE-LIMITED"
    if status != 200:
        return f"HTTP {status}"
    if body.strip() in ("", "{}", "[]", '{"s":"no_data"}'):
        return "EMPTY"
    if '"error' in low or '"information"' in low or '"note"' in low:
        return "ERROR-IN-BODY"
    return "OK"


async def run(env: dict[str, str]) -> int:
    OUT.mkdir(exist_ok=True)
    rows: list[tuple[str, str, str]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for probe in build_probes(env):
            if not env.get(probe.key_name):
                rows.append((probe.name, "SKIPPED", f"{probe.key_name} not set"))
                continue
            try:
                resp = await client.get(probe.url, params=probe.params, headers=probe.headers)
            except httpx.HTTPError as exc:
                rows.append((probe.name, "NETWORK-ERROR", type(exc).__name__))
                continue
            body = resp.text
            try:
                pretty = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except ValueError:
                pretty = body
            (OUT / f"{probe.name}.json").write_text(pretty, encoding="utf-8")
            rows.append((probe.name, verdict(resp.status_code, body), body[:100].replace("\n", " ")))
            # Alpha Vantage free tier throttles bursts; be gentle with everyone.
            await asyncio.sleep(1.5)

    width = max(len(r[0]) for r in rows)
    for name, result, snippet in rows:
        print(f"{name:<{width}}  {result:<14}  {snippet}")
    print(f"\nRaw bodies: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(load_env(ROOT / ".env"))))
