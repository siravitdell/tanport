/**
 * Pure helpers for the calendar page: month grid, event chips, filters. No I/O, no React.
 * Dates are ISO strings (YYYY-MM-DD) handled as UTC calendar dates, never local time.
 */

import { arrow, direction, formatPct } from "./format.ts";

export interface Month {
  year: number;
  month: number; // 1-12
}

export interface GridDay {
  iso: string;
  day: number;
  inMonth: boolean;
}

const pad = (n: number) => String(n).padStart(2, "0");

export function isoDate(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

function utc(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

function toIso(d: Date): string {
  return isoDate(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

export function daysInMonth({ year, month }: Month): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function addMonths({ year, month }: Month, delta: number): Month {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

export function monthOf(iso: string): Month {
  return { year: Number(iso.slice(0, 4)), month: Number(iso.slice(5, 7)) };
}

export function sameMonth(a: Month, b: Month): boolean {
  return a.year === b.year && a.month === b.month;
}

/** The API range for one month: first to last day. */
export function monthRange(m: Month): { from: string; to: string } {
  return { from: isoDate(m.year, m.month, 1), to: isoDate(m.year, m.month, daysInMonth(m)) };
}

/** Weeks Monday → Sunday covering the month, padded with the neighbouring months' days. */
export function monthGrid(m: Month): GridDay[][] {
  const first = utc(isoDate(m.year, m.month, 1));
  const lead = (first.getUTCDay() + 6) % 7; // Monday = 0
  const cells = Math.ceil((lead + daysInMonth(m)) / 7) * 7;
  const weeks: GridDay[][] = [];
  for (let i = 0; i < cells; i++) {
    const d = new Date(first.getTime() + (i - lead) * 86_400_000);
    const day: GridDay = {
      iso: toIso(d),
      day: d.getUTCDate(),
      inMonth: d.getUTCMonth() + 1 === m.month,
    };
    if (i % 7 === 0) weeks.push([]);
    weeks[weeks.length - 1]?.push(day);
  }
  return weeks;
}

/** Today's date in Bangkok as YYYY-MM-DD. */
export function bangkokToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(now);
}

export function isWeekend(iso: string): boolean {
  const dow = utc(iso).getUTCDay();
  return dow === 0 || dow === 6;
}

// --- events ---

export type Filter = "price" | "dividend" | "earnings" | "news" | "macro";
export const FILTERS: Filter[] = ["price", "dividend", "earnings", "news", "macro"];

const FILTER_OF: Record<string, Filter> = {
  price_move: "price",
  split: "price",
  ex_dividend: "dividend",
  dividend_pay: "dividend",
  earnings: "earnings",
  news: "news",
  macro: "macro",
};

export function filterOf(type: string): Filter {
  return FILTER_OF[type] ?? "news";
}

/** Order inside a day cell (the mockup shows the price move first). */
const ORDER = ["price_move", "split", "macro", "earnings", "dividend_pay", "ex_dividend", "news"];

export type ChipKind = "up" | "down" | "pay" | "xd" | "earn" | "news" | "macro";

export interface Chip {
  kind: ChipKind;
  label: string;
  estimate: boolean;
}

export interface EventLike {
  type: string;
  ticker: string | null;
  is_estimate: boolean;
  payload: Record<string, unknown>;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

export function chipFor(e: EventLike): Chip {
  const t = e.ticker ?? "";
  const estimate = e.is_estimate;
  switch (e.type) {
    case "price_move": {
      const pct = str(e.payload.change_pct);
      const dir = pct ? direction(pct) : "flat";
      return {
        kind: dir === "down" ? "down" : "up",
        // 1 decimal so it fits a day cell; the day panel shows 2
        label: pct ? `${arrow(dir)} ${t} ${formatPct(pct, 1)}`.trim() : t,
        estimate,
      };
    }
    case "dividend_pay":
      return { kind: "pay", label: `เงินเข้า · ${t}`, estimate };
    case "ex_dividend":
      return { kind: "xd", label: `XD · ${t}`, estimate };
    case "earnings":
      return { kind: "earn", label: `งบ · ${t}`, estimate };
    case "macro":
      return { kind: "macro", label: `Macro · ${str(e.payload.name) ?? t}`, estimate };
    case "split":
      return { kind: "news", label: `Split · ${t}`, estimate };
    default:
      return { kind: "news", label: `ข่าว · ${t}`, estimate };
  }
}

/** Events allowed by the active filters, in display order. */
export function visibleEvents<E extends EventLike>(events: E[], active: ReadonlySet<Filter>): E[] {
  const rank = (type: string) => {
    const i = ORDER.indexOf(type);
    return i === -1 ? ORDER.length : i;
  };
  return events
    .filter((e) => active.has(filterOf(e.type)))
    .sort((a, b) => rank(a.type) - rank(b.type) || (a.ticker ?? "").localeCompare(b.ticker ?? ""));
}

/** Up to `max` chips, plus how many more are hidden ("+N"). */
export function cellChips(events: EventLike[], max = 3): { chips: Chip[]; more: number } {
  return { chips: events.slice(0, max).map(chipFor), more: Math.max(0, events.length - max) };
}

// --- sparkline ---

/**
 * SVG polyline points for closes (oldest first). Numbers here are only pixel positions;
 * prices shown as text always come from the decimal strings.
 */
export function sparkPoints(closes: string[], width: number, height: number, inset = 2): string {
  if (closes.length < 2) return "";
  const values = closes.map(Number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (width - inset * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const x = inset + i * step;
      const y = max === min ? height / 2 : inset + (1 - (v - min) / span) * (height - inset * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
