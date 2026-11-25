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

// --- errors ---

export class ApiError extends Error {
  readonly status: number;
  readonly retryAfterS: number | null;

  constructor(status: number, message: string, retryAfterS: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterS = retryAfterS;
  }
}

/** FastAPI returns {"detail": "..."} or, for validation errors, {"detail": [{"msg": ...}]}. */
function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
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
};
