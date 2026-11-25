# Data sources — verified 2026-11-24

Probed with real free-tier keys using `backend/scripts/probe_providers.py`.
Trimmed real responses live in `backend/tests/fixtures/<provider>/`.

## Results

| Need | Endpoint | Result |
|---|---|---|
| Latest quote | Finnhub `/quote` | ✅ free |
| Earnings calendar | Finnhub `/calendar/earnings` | ✅ free |
| Daily price history | Finnhub `/stock/candle` | ❌ 403 `You don't have access to this resource.` |
| Dividends | Finnhub `/stock/dividend`, `/stock/dividend2` | ❌ 403 (same) |
| Macro calendar | Finnhub `/calendar/economic` | ❌ 403 (same) — Phase 3 needs another source |
| Daily price history | Tiingo `/tiingo/daily/{ticker}/prices` | ✅ free (stocks + ETFs) |
| Dividends with pay date | Tiingo `/tiingo/corporate-actions/{ticker}/distributions` | ❌ 403, empty body |
| Dividends with pay date | Alpha Vantage `DIVIDENDS` | ✅ free (stocks + ETFs: KO, VOO, SCHD checked) |
| USD/THB | BOT `Stat-ReferenceRate/v2/DAILY_REF_RATE/` | ✅ |

## Decision (Phase 1)

| Protocol | Provider |
|---|---|
| `QuoteProvider` | Finnhub |
| `PriceHistoryProvider` | Tiingo |
| `DividendProvider` | Alpha Vantage |
| `FXProvider` | Bank of Thailand |
| `EarningsProvider` (Phase 2) | Finnhub (per symbol) |
| `NewsProvider` (Phase 2) | Finnhub company-news |
| `MacroProvider` (Phase 3) | TBD |

## Provider notes

### Finnhub
- Base `https://finnhub.io/api/v1`, `token` query param. 60 calls/min.
- `/quote` → `{"c","d","dp","h","l","o","pc","t"}` as floats; `t` = unix seconds.
- Earnings `hour` may be `""` (unknown), `"bmo"`, `"amc"`.

#### Earnings and news (verified 2026-11-25, Phase 2)
| Endpoint | Result |
|---|---|
| `/calendar/earnings?symbol=…&from&to` | ✅ upcoming and past; past rows carry `epsActual` / `revenueActual` |
| `/calendar/earnings?from&to` (whole market) | ⚠️ **capped at 1,500 rows**: a 90-day window comes back truncated (MSFT's 2027-01-26 date was missing) → **call per symbol** (9 holdings = 9 calls/day) |
| `/company-news?symbol=…&from&to` | ✅ stocks **and ETFs** (VOO: ~150 items/week). About **1 year** of history (400 days back = `[]`) |

- Earnings rows: `symbol, date (US date), hour ("bmo"|"amc"|""), quarter, year, epsEstimate, epsActual, revenueEstimate, revenueActual` (floats/null). In the full-market sample: 747 amc, 157 bmo, 596 unknown. ETFs have none.
- News items: `id, category, datetime (unix s), headline, summary, source, url, image, related` (= the queried symbol).
  - **Volume is high**: NVDA returned 248 items for ~1.5 days (Yahoo 208, SeekingAlpha 19, Benzinga 10, CNBC 8). Many are market-wide pieces filed under the symbol → dedupe + importance filtering must happen **before** any LLM call.
  - `url` is a Finnhub redirect (`https://finnhub.io/api/news?id=…`), unique per item; it carries no API key. Near-duplicates (same story, several outlets) have different URLs → also dedupe by headline.
  - `summary` can be empty (~2–6 %), `image` too.
  - **Mojibake from the source**: some SeekingAlpha texts arrive double-encoded (`Buffettâ\u0080\u0099s` for `Buffett's`) → repair at the provider boundary.
  - The same article can be filed under several held symbols, so news is unique per **(ticker, url)**.
  - **Each call returns at most ~250 items** (NVDA 248, MSFT 246, AMZN 241 for a 3-day window) — the newest ones. Polling every 30 min covers it.
  - Measured 2026-11-25, after de-duplication: **~500 items/day** across 9 holdings (NVDA ~210, MSFT/AMZN/GOOGL ~75–80 each, KO/V/ETFs 4–16). Headline ≈ 75 chars, summary ≈ 175 chars. Exact/near-duplicate headlines are rare (12 of 1,173): outlets mostly write their own headlines.

### Tiingo
- `GET https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=YYYY-MM-DD&token=…`
- Limits (Starter): 50 req/hour, 1000 req/day, 500 unique symbols/month. License: internal use only.
- Rows: `date` (`2026-11-23T00:00:00.000Z` = US trading date), `open/high/low/close`, `adj*`,
  `divCash` (on the ex-date), `splitFactor` — all floats.
- Latest row is the previous US session; today's row appears after the close.

### Alpha Vantage
- `GET https://www.alphavantage.co/query?function=DIVIDENDS&symbol=…&apikey=…`
- Limit: **25 requests/day** on the free key → one call per holding per day, nothing else.
- `{"symbol", "data": [{"ex_dividend_date","declaration_date","record_date","payment_date","amount"}]}`
  — newest first, **amount is a string**, dates `YYYY-MM-DD` (may be `"None"`).
- Includes declared future payments (e.g. KO ex 2026-12-01, pay 2026-12-15 seen on 2026-11-24).
- **AMZN returns one bogus row with `amount: "0.0"`** (2022-12-27) → drop rows with amount 0.
- ETFs declare very late (VOO's December payment is not listed yet in late November) → estimates fill the gap.
- Throttle/limit errors come back as HTTP 200 with an `"Information"` or `"Note"` key, not an HTTP error.
- **Also max 1 request per second** (verified 2026-11-24): back-to-back calls get
  `"Please consider spreading out your free API requests more sparingly (1 request per second)"`.
  The text tells the two limits apart: `"per day"` = quota gone until tomorrow, otherwise a burst throttle.

### Bank of Thailand
- Portal: https://portal.api.bot.or.th/ — product "Exchange Rates", plan 200 calls/hour.
- `GET https://gateway.api.bot.or.th/Stat-ReferenceRate/v2/DAILY_REF_RATE/?start_period=YYYY-MM-DD&end_period=YYYY-MM-DD`
- Header `Authorization: <token>` (raw token, no `Bearer` prefix — works as-is).
- **Max 31 days per request** — longer ranges get HTTP 400
  `{"moreInformation":[{"message":"Exceed limit period. Limit period is 31 days"}]}`.
- `result.data.data_detail[] = {"period": "YYYY-MM-DD", "rate": "33.9440000"}` (rate is a string), newest first.
  Only Thai business days.
