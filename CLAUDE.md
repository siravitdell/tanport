# TanPort — Portfolio Dividend & Event Calendar

A small invite-only multi-user web app (a few users: family/friends) that shows, on one calendar, everything happening to the stocks each user holds:
price moves, dividends (in THB, after US withholding tax), earnings, important news, and macro events.

UI reference: screenshots of the approved mockup live in `/docs/mockups/` — match them.

## Goals
- See daily price moves of each holding and of the whole portfolio, in USD and THB.
- See monthly passive income (THB) at a glance.
- Know what is happening to each holding on any given day.
- Get a short morning digest on LINE.

## Tech stack
- **Backend:** Python 3.12+, managed with **uv** (`pyproject.toml` + `uv.lock`)
  - **API:** FastAPI + Pydantic v2, settings via `pydantic-settings`
  - **DB access:** SQLAlchemy 2.0 (async) + `asyncpg`, migrations with **Alembic**
  - **Cache:** `redis` (`redis.asyncio`)
  - **HTTP client:** `httpx` (async) for all external APIs
  - **Scheduler:** APScheduler (runs in the separate worker process)
  - **Money:** `decimal.Decimal`
  - **LLM:** `anthropic` SDK
  - **Logging:** `structlog` (JSON)
  - **Quality:** `ruff` (lint + format), `mypy`, `pytest` + `pytest-asyncio` + `respx`
- **DB / cache:** PostgreSQL, Redis (run both via `docker-compose.yml`)
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind
- **Notifications:** LINE Messaging API (LINE Notify is discontinued — do not use it)
- **LLM (news summary):** Claude API, model name from env var `LLM_MODEL`

## Repo layout
```
/backend
  pyproject.toml
  /app
    main.py         # FastAPI app (REST server)
    worker.py       # APScheduler entrypoint (scheduled jobs)
    config.py       # pydantic-settings, reads env vars
    /api            # routers + request/response schemas (thin)
    /domain         # pure business rules: tax, FX, estimates, portfolio change, projections (no I/O)
    /providers      # Protocol interfaces + implementations (finnhub, bot_fx, ...)
    /store          # SQLAlchemy models + repositories
    /jobs           # sync jobs
  /migrations       # Alembic
  /tests
    /fixtures       # recorded API responses
/frontend
docker-compose.yml
.env.example
```

## Domain rules (important)
- **Money:** never use float for money. Use `Decimal` in Python, `Numeric` in SQLAlchemy/Postgres, strings in JSON.
  - Providers return floats: convert with `Decimal(str(value))` at the provider boundary, never `Decimal(value)`.
  - Round only for display, with `ROUND_HALF_UP`.
- **Net dividend (THB)** = `shares × dividend_per_share × (1 − withholding_rate) × usd_thb`
  - `withholding_rate` default **0.15** (US–Thailand treaty with W-8BEN). Configurable per user; 0.30 if no W-8BEN.
  - Use the FX rate of the **pay date** (fallback: latest available rate). Show which rate was used.
- **Ex-dividend date ≠ pay date.** Shares must be held *before* the ex-date. Show both as separate events.
- **Positions over time come from the trade log** (`ShareLedger`): a dividend counts the shares held at the end of the day before its ex-date (if the ex-date is still ahead: the shares held now); a position sold later keeps the dividends it earned. Portfolio history uses the shares held at the end of each day; calendar events show only for positions held on that day.
- For projected (not yet declared) dividends, estimate from the last 4 payments and mark `is_estimate = true`.
- **Time:** store everything in UTC; display in `Asia/Bangkok`. Earnings "before open / after close" must be converted to Thai time.
- Some holdings pay no dividend (e.g. AMZN) — handle gracefully.
- **Portfolio daily change %** = Σ (holding weight × holding change %), weights by market value at the previous close. Also show the change in THB.
- **Big move:** a holding moving ≥ ±3% in one day becomes a `price_move` event on that day (threshold configurable). The day detail shows it next to that ticker's news for the same day.
- Weekends, US market holidays and future days have no price data — show "market closed" / "no data yet", never 0%.
- US market hours in Thai time: 21:30–04:00 (US standard time), 20:30–03:00 (US daylight time). Derive from `America/New_York`, never hard-code.

## Data sources
- **Finnhub** (free tier: 60 calls/min): quotes, company news, earnings calendar.
  - **Verify** whether the daily candles (price history), dividends and economic-calendar endpoints are on the free tier before relying on them.
- Put every provider behind a `typing.Protocol` (`QuoteProvider`, `PriceHistoryProvider`, `DividendProvider`, `EarningsProvider`, `NewsProvider`, `MacroProvider`, `FXProvider`) so a fallback can be swapped in and tests can use fakes.
  - `yfinance` is allowed as a **prototype-only** fallback for price history and dividends (unofficial, can break).
- **FX:** Bank of Thailand API (USD/THB reference rate), cached in Redis for 24h.
- Respect rate limits with a Redis-backed limiter shared by all jobs.
- API keys come from env vars only. Never commit secrets; keep `.env` in `.gitignore` and maintain `.env.example`.

## Users & auth
- Multi-user, **invite-only**: `POST /api/auth/register` requires `INVITE_CODE` from env (empty = registration disabled).
- Passwords: stdlib `hashlib.scrypt` (no extra crypto dependency). Sessions: random token in an HttpOnly, SameSite=Lax cookie (`tanport_session`); only its SHA-256 is stored.
- **Per-user data:** `trades`, `holdings`, `user_settings`, `portfolio_daily`. Every query on them is scoped by `user_id`; another user's id must return 404, never the row.
- **Shared market data:** `prices`, `events`, `news`, `fx_rates` — fetched once per distinct ticker across all users. Never store user-specific amounts (e.g. net THB) in shared tables; compute them per user at read time.
- Free-tier quotas are shared by all users (Alpha Vantage 25/day ≈ 25 distinct dividend tickers in total). If exceeded, spread syncs over several days and show data age in the UI.

## Data model (starting point)
- `users(id, email unique lower-case, password_hash, display_name, is_active, created_at, updated_at)`
- `user_sessions(token_hash PRIMARY KEY, user_id, created_at, expires_at)`
- `user_settings(user_id PRIMARY KEY, withholding_rate, big_move_threshold_pct, dca_split jsonb)` — created at registration
- `trades(id, user_id, ticker, side buy|sell, trade_date, shares, price_usd, fee_usd, usd_thb, created_at)` — the source of truth for positions. `usd_thb` is the rate actually paid (defaults to the BOT rate of `trade_date`). A sale may never exceed the shares held on its date (also after a delete/import → 409).
- `holdings(id, user_id, ticker, shares numeric, avg_cost_usd numeric, created_at, updated_at, UNIQUE (user_id, ticker))` — **derived** from `trades` (average-cost method, fees included) and rebuilt after every trade change; only open positions. Never write it directly.
- `prices(ticker, trade_date, open, high, low, close numeric, change_pct numeric, PRIMARY KEY (ticker, trade_date))` — daily closes
- `portfolio_daily(user_id, trade_date, value_usd, value_thb, change_pct, change_thb, usd_thb, fx_rate_date, PRIMARY KEY (user_id, trade_date))` — derived after each close
- `events(id, type, ticker nullable, event_date, event_time_utc nullable, payload jsonb, is_estimate bool, source, created_at)`
  - `type` ∈ `price_move | ex_dividend | dividend_pay | earnings | split | macro`
  - unique on `(type, ticker, event_date, source)` → upserts are idempotent
- `news(id, ticker, published_at, headline, headline_key, url, source, provider, provider_id, snippet, summary, importance smallint 1-5, summarized_at, created_at, UNIQUE (ticker, url))` — `snippet` = provider's English summary; `summary`/`importance` = LLM output (NULL until scored). Unique per (ticker, url) because one article can be filed under several holdings.
- `fx_rates(date, pair, rate)`

## Jobs (`app/worker.py`, APScheduler)
Run exactly one worker process. Each job takes a Redis lock so an overlapping run is skipped.

| Job | Schedule (Asia/Bangkok) | What |
|---|---|---|
| sync_quotes | every 5 min, US market hours only | latest quote per holding → Redis (not Postgres) |
| sync_daily_close | daily 05:30 | yesterday's closes → `prices` (once per distinct ticker), compute `portfolio_daily` for every user, create `price_move` events |
| sync_dividends | daily 06:00 | declared + estimated dividends for all holdings |
| sync_earnings | daily 06:00 | next 90 days of earnings |
| sync_macro | daily 06:00 | FOMC, CPI, NFP |
| sync_news | every 30 min | fetch → dedupe by URL & near-duplicate headline (LLM summary + importance: Phase 4) |
| send_digest | daily 07:00 | LINE message: today/tonight events + top news |

All jobs must be idempotent and safe to re-run.

## REST API
All endpoints except `/api/health` and `/api/auth/{register,login}` require a logged-in session and act on the current user's data.
- `POST /api/auth/register` (email, password, invite_code), `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `GET /api/holdings` (read-only, derived from trades)
- `GET/POST /api/trades`, `DELETE /api/trades/{id}`
- `POST /api/trades/import` (raw `text/csv` body: `date,side,ticker,shares,price_usd,fee_usd,usd_thb`; only ticker, shares, price_usd required; `avg_cost_usd` accepted for price_usd — all-or-nothing)
- `GET /api/portfolio` → positions valued at the latest price and today's rate: cost (USD/THB), unrealized P/L split into price and FX parts, realized P/L (average cost), weights
- `GET /api/fx?date=…` → the USD/THB rate that applies to a date (pre-fills the trade form)
- `GET /api/quotes` → latest price, day change % and weight for every holding + portfolio value/change
- `GET /api/prices?ticker=…&days=14` → daily closes (for sparklines)
- `GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD` → per day: portfolio change % (if trading day) + events
- `GET /api/day/{date}` → portfolio change, every holding's change sorted by |change|, events, all news
- `GET /api/income/monthly?year=YYYY` → net THB per month (actual vs estimate)
- `GET /api/income/projection?monthly_dca_thb=…&years=…` → projected dividend income
- `GET /api/settings`, `PUT /api/settings` (withholding rate, DCA split)

## Frontend pages
- **Login / Register** (register asks for the invite code). Unauthenticated users are redirected here.
- **Calendar (month view):**
  - Top cards: portfolio value today (THB, change % and THB), net dividends this month, ex-dividend count, next earnings.
  - "Prices today" strip: one card per holding — price, change %, weight, 14-trading-day sparkline.
  - Each day cell: portfolio change % (top right), up to 3 event chips, "+N more".
  - Filters: Price · Dividends · Earnings · News · Macro.
  - Only news with importance ≥ 4 shown on the grid (none until news is scored, Phase 4).
  - Up = green + ▲ + "+", down = red + ▼ + "−" (never color alone).
- **Day detail panel:** portfolio change for the day, all holdings sorted by |change|, all events + summarised news, links to sources.
- **Income:** bar chart of monthly net THB (actual vs estimated), yearly total, yield on cost per holding.
- **Portfolio (พอร์ต):** record a buy/sell (form: ticker, date, shares, price, fee, rate pre-filled from BOT), holdings table (shares, average cost, last price, value, P/L, weight), trade history with delete, CSV import. Mockup: `พอร์ต · บันทึกซื้อขาย@2x.png`.
- **Settings.**

## Theming (light + dark)
- Two themes: **light** ("Ink & Mint") and **dark** ("Midnight Terminal"). Default = follow the OS (`prefers-color-scheme`); a toggle in the header overrides it and is remembered in `localStorage`.
- **Never hard-code colors in components.** Define every color once as a CSS variable (`:root` = light, `[data-theme="dark"]` = dark) and map them in the Tailwind config; components use only these tokens.

| Token | Light | Dark |
|---|---|---|
| `bg` | `#F6F6F3` | `#0E1116` |
| `surface` | `#FFFFFF` | `#171B22` |
| `surface-2` | `#F6F6F3` | `#1E2530` |
| `ink` | `#16181D` | `#E8EAED` |
| `ink-2` | `#3A3D44` | `#C9CFD6` |
| `muted` | `#5E626B` | `#9AA3AE` |
| `line` | `#E3E3DE` | `#2A303A` |
| `line-strong` | `#D4D4CE` | `#3A424E` |
| `hero` (dark cards) | `#16181D` | `#1E2530` |
| `hero-accent` | `#6FD3A6` | `#3FD08A` |
| `up` | `#0B6B47` | `#3FD08A` |
| `down` | `#B42318` | `#FF7A6E` |
| `pay` bg / text | `#E2F3EA` / `#0B5A43` | `#123326` / `#6FE3A8` |
| `xd` bg / text | `#F3EBD9` / `#6A4A0E` | `#3A2E12` / `#F2C46B` |
| `earn` bg / text | `#E5ECFB` / `#1D43AE` | `#17264A` / `#9DB8FF` |
| `news` bg / text | `#EDEDEA` / `#383B42` | `#232A34` / `#C9CFD6` |
| `macro` bg / text | `#FBE8D9` / `#953B06` | `#3D2414` / `#FFB07A` |

- Fonts: **IBM Plex Sans Thai** (UI), **IBM Plex Mono** (all numbers, prices, %).
- Text must meet WCAG AA contrast (4.5:1) in both themes.

## Holdings of the first user (imported via CSV)
VOO, QQQM, SCHD, V, MSFT, KO, GOOGL, NVDA, AMZN
Default DCA split for new users: VOO 70 / QQQM 20 / SCHD 10.

## Milestones
1. **Phase 1:** docker-compose, migrations, holdings CRUD + CSV import, quotes + daily closes, portfolio daily change, dividend sync, FX, monthly calendar with price %, prices strip, income chart.
2. **Phase 2:** earnings + news sync (de-duplicated, no LLM yet), big-move events, day detail view (raw headlines with links until news is scored).
3. **Phase 3:** LINE digest, macro events, projection page, polish.
4. **Phase 4 (last):** LLM news summary + importance; then news chips on the grid (importance ≥ 4), "likely cause" news picked by importance, and top news in the LINE digest.

Finish and verify one phase before starting the next.

## Conventions
- `pytest.mark.parametrize` unit tests for everything in `app/domain` (tax, FX, estimates, portfolio change, projection).
- Provider implementations get tests with recorded fixtures mocked via `respx` — no live API calls in tests.
- `make dev`, `make test`, `make lint`, `make migrate` must work (`lint` = `ruff check` + `ruff format --check` + `mypy`, plus `eslint` + `tsc --noEmit` for the frontend).
- Frontend: Next.js 16 — read `frontend/AGENTS.md` and the docs bundled in `frontend/node_modules/next/dist/docs/` before using a Next.js API (middleware is now `proxy.ts`, `next lint` is gone). Pure helpers in `frontend/src/lib` get `node --test` tests (`*.test.ts`, no test framework dependency). Money stays a string in the frontend too: format it with `lib/format.ts`, never `Number()`/`parseFloat()`.
- Type hints everywhere; async I/O end to end (no blocking calls inside async code).
- Structured logging with `structlog`. Raise specific exceptions; never swallow errors silently.
- Keep routers thin; business logic lives in `app/domain`.
- Ask before adding a new dependency that isn't listed above.
