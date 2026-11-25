/**
 * Pure helpers for the income page. Amounts stay decimal strings; the only floats are bar
 * heights (pixel geometry), never displayed money.
 */

import { addDecimals } from "./format.ts";

const DECIMAL_RE = /^([+-]?)(\d+)(?:\.(\d+))?$/;
const SCALE = 6;

function scaled(value: string): bigint {
  const m = DECIMAL_RE.exec(value.trim());
  if (!m) throw new Error(`not a decimal string: ${JSON.stringify(value)}`);
  const [, sign, int = "", frac = ""] = m;
  const n = BigInt(int + frac.padEnd(SCALE, "0").slice(0, SCALE));
  return sign === "-" ? -n : n;
}

/** part / whole as a whole percent, half-up: ratioPct("94", "100") → "94". null if whole ≤ 0. */
export function ratioPct(part: string, whole: string): string | null {
  const p = scaled(part);
  const w = scaled(whole);
  if (w <= BigInt(0)) return null;
  const twice = (p * BigInt(200)) / w; // percent × 2, truncated
  return ((twice + BigInt(1)) / BigInt(2)).toString();
}

export function isPositive(value: string): boolean {
  return scaled(value) > BigInt(0);
}

export interface MonthLike {
  month: number;
  received_thb: string;
  upcoming_thb: string;
}

export interface Bar {
  month: number;
  received: string;
  upcoming: string;
  total: string;
  /** 0..1 of the tallest month, for drawing only */
  receivedRatio: number;
  upcomingRatio: number;
}

export function monthBars(months: MonthLike[]): Bar[] {
  const totals = months.map((m) => addDecimals([m.received_thb, m.upcoming_thb]));
  const max = Math.max(0, ...totals.map(Number));
  return months.map((m, i) => ({
    month: m.month,
    received: m.received_thb,
    upcoming: m.upcoming_thb,
    total: totals[i] ?? "0",
    receivedRatio: max > 0 ? Number(m.received_thb) / max : 0,
    upcomingRatio: max > 0 ? Number(m.upcoming_thb) / max : 0,
  }));
}

export interface Concentration {
  topMonths: number[]; // calendar order
  sharePct: string; // of the year's total
  emptyMonths: number[];
}

/**
 * "Income is concentrated in N months": the top `top` months by amount and their share.
 * null when there is nothing to say (no income, or too few paying months to be "concentrated").
 */
export function concentration(months: MonthLike[], top = 4): Concentration | null {
  const totals = months.map((m) => ({ month: m.month, total: addDecimals([m.received_thb, m.upcoming_thb]) }));
  const paying = totals.filter((t) => isPositive(t.total));
  if (paying.length <= 1) return null;
  const year = addDecimals(totals.map((t) => t.total));
  const best = [...paying]
    .sort((a, b) => {
      const diff = scaled(b.total) - scaled(a.total);
      return diff > BigInt(0) ? 1 : diff < BigInt(0) ? -1 : a.month - b.month;
    })
    .slice(0, Math.min(top, paying.length));
  const share = ratioPct(addDecimals(best.map((b) => b.total)), year);
  if (share === null) return null;
  return {
    topMonths: best.map((b) => b.month).sort((a, b) => a - b),
    sharePct: share,
    emptyMonths: totals.filter((t) => !isPositive(t.total)).map((t) => t.month),
  };
}
