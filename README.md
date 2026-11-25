# TanPort

**Portfolio dividend & event calendar** — one calendar for everything happening to the US stocks you hold:
daily price moves, dividends in Thai baht after US withholding tax, earnings, important news and macro events.

- Daily price change of each holding and of the whole portfolio, in USD and THB
- Monthly passive income (THB, net of the 15 % W-8BEN withholding)
- What happened to each holding on any given day
- A short morning digest on LINE

Small, invite-only, multi-user: each user has their own holdings and settings; market data is shared.

> **Status: Phase 1 complete.** Auth, holdings, quotes, daily closes, calendar, dividends/income, FX,
> the scheduled worker, and the web app (login, calendar, income; light/dark). Since then: a trade log
> (buys/sales) that positions and P/L are computed from, with a portfolio page and a settings page.
> See [Roadmap](#roadmap).

UI reference: [`docs/mockups/`](docs/mockups/)

---

## Tech stack

| Part | Tools |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic |
| Jobs | APScheduler worker (separate process), Redis locks and rate limits |
| Data | PostgreSQL 16, Redis 7 (both via Docker Compose) |
| Frontend | Next.js 16 (App Router) + TypeScript + Tailwind 4 |
| Quality | ruff, mypy `--strict`, pytest + pytest-asyncio + respx |
| Tooling | [uv](https://docs.astral.sh/uv/), GNU make |

Money is `Decimal` in Python, `Numeric` in Postgres and a string in JSON. Never a float.

## Data sources

| Data | Provider (free tier) |
|---|---|
| Latest quotes, earnings calendar | [Finnhub](https://finnhub.io) |
| Daily price history | [Tiingo](https://www.tiingo.com) |
| Dividends (ex date, pay date, amount) | [Alpha Vantage](https://www.alphavantage.co) |
| USD/THB reference rate | [Bank of Thailand API](https://portal.api.bot.or.th/) |

Finnhub's free tier blocks candles and dividends. Each provider's limits and quirks are recorded in
[`docs/data-sources.md`](docs/data-sources.md).

---

## Getting started

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Windows: `winget install astral-sh.uv`). uv installs Python 3.12 for you.
- GNU make (Windows: `winget install ezwinports.make`)
- [Node.js](https://nodejs.org/) 22.18 or newer (the frontend unit tests run TypeScript directly with `node --test`)

### 2. Configure

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `FINNHUB_API_KEY` | https://finnhub.io/dashboard |
| `TIINGO_API_KEY` | https://www.tiingo.com/account/api/token |
| `ALPHAVANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key |
| `BOT_API_TOKEN` | https://portal.api.bot.or.th/: sign up, subscribe to **Exchange Rates**, then copy the token from *My apps* |
| `INVITE_CODE` | Any hard-to-guess string. People need it to register; leave it empty to close registration. |

`.env` is git-ignored. Never commit it.

> Postgres is published on host port **5433**, not 5432, so it doesn't clash with a locally installed PostgreSQL.

### 3. Run

```bash
make install   # backend (uv sync) + frontend (npm ci) dependencies
make migrate   # starts Postgres + Redis, applies migrations
make dev       # web on http://localhost:3000, API on :8000, worker
```

Open http://localhost:3000 and register with the invite code. Interactive API docs: http://localhost:8000/docs

The browser only talks to the Next.js origin: `/api/*` is forwarded to FastAPI (`API_ORIGIN`, default
`http://localhost:8000`), so the session cookie is first-party and no CORS is needed.

### 4. Create an account and record your trades

Register at http://localhost:3000 with the invite code, then open **พอร์ต** and record each buy and sale
(ticker, date, shares, price, fee; the USD/THB rate is pre-filled from the Bank of Thailand for that date
and can be changed to the rate your broker actually gave). Shares held, average cost and profit/loss are
computed from these trades (average-cost method, fees included). A sale can never exceed what was held
on its date.

Or import many trades at once with **นำเข้าจากไฟล์ CSV**:

```csv
date,side,ticker,shares,price_usd,fee_usd,usd_thb
2026-08-04,buy,VOO,1.5,585.40,0,33.20
2026-11-09,sell,NVDA,2,153.87,0,
```

Only `ticker`, `shares` and `price_usd` are required: `date` defaults to today, `side` to buy (`ซื้อ`/`ขาย` work too),
`fee_usd` to 0, and an empty `usd_thb` uses the Bank of Thailand rate of that date. An old
`ticker,shares,avg_cost_usd` holdings file is accepted as buys at the average cost today.
The import is **all-or-nothing**: if any row is invalid, nothing is saved, and the response lists each bad row by line number.

### 5. Load market data

`make dev` also starts the **worker**, which runs every job on a schedule (Bangkok time):

| Job | When |
|---|---|
| `sync_quotes` | every 5 min (it only fetches during US market hours + 20 min) |
| `sync_daily_close` | 05:30, again at 08:30 in case Tiingo publishes late |
| `sync_dividends` | 06:00 |
| `sync_fx` | 18:30, and once at worker start-up |
| `cleanup_sessions` | 04:00 |

Run exactly one worker. Each job holds a Redis lock, so overlapping runs are skipped, and every job is safe to re-run.
The last success and the last error for each job are stored in the Redis hashes `jobs:last_success` / `jobs:last_error`.

Any job can also be run by hand, for example right after importing holdings:

```bash
cd backend
uv run python -m app.jobs.sync_fx --since 2025-01-01   # USD/THB history (BOT: 31 days per request)
uv run python -m app.jobs.sync_quotes --force          # latest quotes (normally only during US market hours)
uv run python -m app.jobs.sync_daily_close             # daily closes (~100 days back the first time),
                                                       # big-move events, every user's portfolio history
uv run python -m app.jobs.sync_dividends               # declared + estimated dividends (Alpha Vantage:
                                                       # 25 calls/day — the rest is deferred to the next run)
```

Then `GET /api/quotes` returns today's prices, weights and portfolio value in USD and THB, and
`GET /api/calendar?from=…&to=…` returns the daily portfolio change and events.

---

## Development

| Command | What it does |
|---|---|
| `make up` / `make down` | Start / stop Postgres and Redis |
| `make install` | `uv sync` + `npm ci` |
| `make dev` | API, worker and Next.js dev server; saving a file under `backend/app/` restarts the API and the worker |
| `make migrate` | `alembic upgrade head` |
| `make test` | Starts infra, runs pytest, then the frontend unit tests (`node --test`) |
| `make lint` | `ruff check` + `ruff format --check` + `mypy --strict`, then `eslint` + `tsc --noEmit` |
| `make fmt` | Auto-format and auto-fix |

Tests use a separate database (`tanport_test`) and Redis DB 15.
Each test runs inside a transaction that is rolled back afterwards.
Provider tests replay recorded responses from `backend/tests/fixtures/` with respx; no live API calls.

New migration:

```bash
cd backend
uv run alembic revision --autogenerate -m "describe the change"
```

`tests/store/test_migrations.py` runs `alembic check` and fails if the models and migrations drift apart.

### Project layout

```
backend/
  app/
    api/         FastAPI routers + request/response schemas (thin)
    domain/      pure business rules: tax, FX choice, portfolio change, market hours, estimates (no I/O)
    providers/   typing.Protocol interfaces + Finnhub / Tiingo / Alpha Vantage / BOT clients
    services/    orchestration of providers + store + Redis (e.g. FX refresh)
    store/       SQLAlchemy models + repositories, Redis quote cache
    jobs/        sync jobs (each takes a Redis lock; runnable with `python -m`)
    main.py      API app          worker.py   scheduler entrypoint
  migrations/    Alembic
  tests/         mirrors app/; fixtures/ holds recorded API responses
frontend/
  src/
    app/         routes: login/, (app)/ = pages that need a session (calendar, income)
    components/  header, theme toggle, auth provider, calendar/ (cards, prices strip, month grid,
                 day panel), income/ (cards, monthly chart, per-holding table),
                 portfolio/ (trade form, CSV import, holdings, history), settings/
    lib/         typed API client, string-based number formatting, month grid / event chips,
                 income bars (+ *.test.ts), theme
    proxy.ts     no session cookie → /login
    app/globals.css  every color as a CSS variable (light + dark), mapped to Tailwind
docs/            mockups, data-source notes
```

Project rules and conventions for contributors (and for Claude Code) live in [`CLAUDE.md`](CLAUDE.md).

### Key rules

- **Net dividend (THB)** = shares × dividend per share × (1 − withholding) × USD/THB, using the rate on the **pay date**.
  If there is no rate for that day, the latest earlier rate is used, and the UI shows which date's rate it was.
- The ex-dividend date and the pay date are separate events.
- Store times in UTC; display them in `Asia/Bangkok`. US market hours come from `America/New_York`.
- Weekends, holidays and days with no data show "market closed" / "no data yet", never 0 %.

---

## API (so far)

All endpoints except health, register and login need a logged-in session cookie.

| Method | Path | |
|---|---|---|
| `GET` | `/api/health` | liveness |
| `POST` | `/api/auth/register` · `/login` · `/logout` | invite-only; login is rate-limited |
| `GET` | `/api/auth/me` | current user |
| `GET` `POST` | `/api/trades` | trade log (newest first) / record a buy or sale (`usd_thb` optional) |
| `DELETE` | `/api/trades/{id}` | refused (409) if a later sale would no longer be covered |
| `POST` | `/api/trades/import` | CSV body (`text/csv`), all-or-nothing |
| `GET` | `/api/holdings` · `/api/holdings/{id}` | read-only: derived from the trades |
| `GET` | `/api/portfolio` | positions at the latest price and today's rate: cost, unrealized P/L (price vs FX part), realized P/L, weights |
| `GET` | `/api/fx?date=YYYY-MM-DD` | the USD/THB rate that applies to a date |
| `GET` `PUT` | `/api/settings` | withholding rate, big-move threshold, DCA split |
| `GET` | `/api/quotes` | market status, FX used, portfolio value/change, per-holding price and weight |
| `GET` | `/api/prices?ticker=VOO&days=14` | recent daily closes (sparklines) |
| `GET` | `/api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD` | per day: status (`ok`/`no_data`/`future`/`closed`), portfolio change, events (≤ 62 days); `period` = compounded change over the range |
| `GET` | `/api/income/monthly?year=YYYY` | net THB dividends per month (received vs upcoming), every payment with the FX rate used, per-holding totals and yield on cost |

## Roadmap

**Phase 1**: core
- [x] Docker Compose, uv + FastAPI skeleton, migrations
- [x] Domain rules (tax, FX, portfolio change, NYSE calendar, dividend estimates)
- [x] Invite-only multi-user auth, holdings CRUD + CSV import, settings
- [x] Provider interfaces, shared Redis rate limiter, job locks
- [x] USD/THB from Bank of Thailand
- [x] Live quotes + `/api/quotes`
- [x] Daily closes, portfolio history, big-move events, `/api/calendar`, `/api/prices`
- [x] Dividends (declared + estimated) and `/api/income/monthly`
- [x] Scheduled worker
- [x] Web UI: login, calendar month view, prices strip, income chart, light/dark themes
- [x] Trade log (buy/sell, average cost, realized/unrealized P/L split into price and FX), portfolio page, settings page

**Phase 2**: earnings and news sync, LLM news summaries with an importance score, day detail view

**Phase 3**: LINE morning digest, macro events (FOMC/CPI/NFP), DCA income projection, polish
