/**
 * Typed client for the FastAPI backend. Same origin: next.config.ts forwards /api/* to FastAPI,
 * so the HttpOnly session cookie is sent automatically.
 *
 * Decimal fields are strings (money is never a JS number); format them with lib/format.ts.
 * Types mirror the Pydantic response models in backend/app/api/.
 */

export type DecimalString = string;
export type IsoDate = string; // YYYY-MM-DD
export type IsoDateTime = string; // ISO 8601 with offset (UTC)

// --- auth (backend/app/api/auth.py) ---

export interface User {
  id: number;
  email: string;
  display_name: string | null;
}

export interface RegisterBody {
  email: string;
  password: string;
  invite_code: string;
  display_name?: string | null;
}

// --- quotes (backend/app/api/quotes.py) ---

export interface QuotesResponse {
  market: { is_open: boolean; last_session_date: IsoDate; next_open_utc: IsoDateTime };
  fx: { usd_thb: DecimalString; rate_date: IsoDate; is_fallback: boolean } | null;
  portfolio: {
    value_usd: DecimalString;
    value_thb: DecimalString;
    change_pct: DecimalString;
    change_usd: DecimalString;
    change_thb: DecimalString;
    excluded: string[];
  } | null;
  holdings: Array<{
    ticker: string;
    shares: DecimalString;
    status: "ok" | "no_quote";
    price: DecimalString | null;
    prev_close: DecimalString | null;
    change: DecimalString | null;
    change_pct: DecimalString | null;
    weight_pct: DecimalString | null;
    value_usd: DecimalString | null;
    value_thb: DecimalString | null;
    as_of_utc: IsoDateTime | null;
  }>;
  as_of_utc: IsoDateTime | null;
}

// --- prices (backend/app/api/prices.py) ---

export interface PricesResponse {
  ticker: string;
  points: Array<{ trade_date: IsoDate; close: DecimalString; change_pct: DecimalString | null }>; // oldest first
}

// --- calendar (backend/app/api/calendar.py) ---

export type EventType = "price_move" | "ex_dividend" | "dividend_pay" | "earnings" | "split" | "macro";
export type DayStatus = "ok" | "no_data" | "future" | "closed";

export interface CalendarEvent {
  id: number;
  type: EventType | (string & {});
  ticker: string | null;
  event_date: IsoDate;
  event_time_utc: IsoDateTime | null;
  is_estimate: boolean;
  payload: Record<string, unknown>;
}

export interface CalendarDay {
  date: IsoDate; // US trade date
  status: DayStatus;
  portfolio: {
    value_thb: DecimalString;
    change_pct: DecimalString | null;
    change_thb: DecimalString | null;
  } | null;
  events: CalendarEvent[];
}

export interface CalendarResponse {
  from: IsoDate;
  to: IsoDate;
  period: { change_pct: DecimalString; change_thb: DecimalString; trading_days: number } | null;
  days: CalendarDay[];
}

// --- income (backend/app/api/income.py) ---

export interface IncomePayment {
  ticker: string;
  ex_date: IsoDate | null;
  pay_date: IsoDate;
  dps: DecimalString;
  shares: DecimalString;
  is_estimate: boolean;
  status: "received" | "upcoming";
  gross_usd: DecimalString | null;
  tax_usd: DecimalString | null;
  net_usd: DecimalString | null;
  net_thb: DecimalString | null;
  usd_thb: DecimalString | null;
  fx_rate_date: IsoDate | null;
  fx_is_fallback: boolean | null;
}

export interface IncomeResponse {
  year: number;
  withholding_rate: DecimalString;
  totals: {
    net_thb: DecimalString;
    gross_thb: DecimalString;
    tax_thb: DecimalString;
    received_thb: DecimalString;
    upcoming_thb: DecimalString;
    monthly_avg_thb: DecimalString;
    yield_on_cost_pct: DecimalString | null;
  };
  months: Array<{
    month: number; // 1-12
    received_thb: DecimalString;
    upcoming_thb: DecimalString;
    payments: IncomePayment[];
  }>;
  holdings: Array<{
    ticker: string;
    pays_dividend: boolean;
    pay_months: number[];
    net_usd: DecimalString;
    net_thb: DecimalString;
    yield_on_cost_pct: DecimalString | null;
  }>;
  missing_fx: IsoDate[];
}

// --- settings (backend/app/api/settings.py) ---

export interface SettingsResponse {
  withholding_rate: DecimalString;
  big_move_threshold_pct: DecimalString;
  dca_split: Record<string, DecimalString>;
  updated_at: IsoDateTime;
}

// --- trades & portfolio (backend/app/api/trades.py, portfolio.py) ---

export type Side = "buy" | "sell";

export interface Trade {
  id: number;
  side: Side;
  ticker: string;
  trade_date: IsoDate;
  shares: DecimalString;
  price_usd: DecimalString;
  fee_usd: DecimalString;
  usd_thb: DecimalString;
  cash_usd: DecimalString; // + money in (sell), − money out (buy)
  cash_thb: DecimalString;
  created_at: IsoDateTime;
}

export interface TradeBody {
  side: Side;
  ticker: string;
  trade_date: IsoDate;
  shares: DecimalString;
  price_usd: DecimalString;
  fee_usd: DecimalString;
  usd_thb: DecimalString | null; // null: the BOT rate of trade_date
}

export interface FxResponse {
  usd_thb: DecimalString;
  rate_date: IsoDate;
  is_fallback: boolean;
}

export interface Position {
  ticker: string;
  shares: DecimalString;
  avg_cost_usd: DecimalString;
  avg_cost_thb: DecimalString;
  cost_usd: DecimalString;
  cost_thb: DecimalString;
  price_usd: DecimalString | null;
  price_source: "quote" | "close" | null;
  value_usd: DecimalString | null;
  value_thb: DecimalString | null;
  unrealized_thb: DecimalString | null;
  unrealized_pct: DecimalString | null;
  price_pl_thb: DecimalString | null;
  fx_pl_thb: DecimalString | null;
  weight_pct: DecimalString | null;
  trades: number;
}

export interface PortfolioResponse {
  fx: FxResponse;
  positions: Position[];
  totals: {
    value_usd: DecimalString;
    value_thb: DecimalString;
    cost_usd: DecimalString;
    cost_thb: DecimalString;
    unrealized_thb: DecimalString;
    unrealized_pct: DecimalString | null;
    price_pl_thb: DecimalString;
    fx_pl_thb: DecimalString;
    realized_thb: DecimalString;
    realized_usd: DecimalString;
    trades: number;
    unpriced: string[];
  } | null;
}

export interface CsvRowError {
  line: number;
  column: string | null;
  message: string;
}

// --- errors ---

export class ApiError extends Error {
  readonly status: number;
  readonly retryAfterS: number | null;
  /** FastAPI's `detail` as sent (a string, a validation list, or e.g. {message, errors} for CSV). */
  readonly detail: unknown;

  constructor(status: number, message: string, retryAfterS: number | null = null, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterS = retryAfterS;
    this.detail = detail;
  }

  /** Per-row problems of a rejected CSV import, if that is what this error carries. */
  get csvErrors(): CsvRowError[] {
    const d = this.detail;
    if (d && typeof d === "object" && "errors" in d && Array.isArray((d as { errors: unknown }).errors)) {
      return (d as { errors: CsvRowError[] }).errors;
    }
    return [];
  }
}

/** FastAPI returns {"detail": "..."} or, for validation errors, {"detail": [{"msg": ...}]}. */
function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : null))
        .filter((m): m is string => m !== null);
      if (msgs.length) return msgs.join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  if (res.status === 204) return undefined as T;

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(
      res.status,
      detailMessage(body, `${res.status} ${res.statusText}`),
      Number.isFinite(retry) && retry > 0 ? retry : null,
      body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null,
    );
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  get: <T>(path: string) => request<T>(path),

  me: () => request<User>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", json({ email, password })),
  register: (body: RegisterBody) => request<User>("/api/auth/register", json(body)),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  quotes: () => request<QuotesResponse>("/api/quotes"),

  createTrade: (body: TradeBody) => request<Trade>("/api/trades", json(body)),
  deleteTrade: (id: number) => request<void>(`/api/trades/${id}`, { method: "DELETE" }),
  importTrades: (csv: string) =>
    request<{ imported: number }>("/api/trades/import", {
      method: "POST",
      body: csv,
      headers: { "Content-Type": "text/csv" },
    }),
  fx: (date: IsoDate) => request<FxResponse>(`/api/fx?date=${date}`),

  updateSettings: (body: Omit<SettingsResponse, "updated_at">) =>
    request<SettingsResponse>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
};
