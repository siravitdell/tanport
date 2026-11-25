"use client";

import { useMemo, useState, useSyncExternalStore } from "react";

import type {
  CalendarDay,
  CalendarResponse,
  IncomePayment,
  IncomeResponse,
  QuotesResponse,
  SettingsResponse,
  UpcomingEarnings,
} from "@/lib/api";
import {
  FILTERS,
  type Filter,
  type Month,
  addMonths,
  bangkokToday,
  monthOf,
  monthRange,
  sameMonth,
} from "@/lib/calendar";
import { formatMonthYear } from "@/lib/dates";
import { arrow, direction, formatDecimal, formatPct, shiftDecimal } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import { DayPanel } from "./DayPanel";
import { MonthGrid } from "./MonthGrid";
import { PriceStrip } from "./PriceStrip";
import { DIR_TEXT, FILTER_META } from "./styles";
import { SummaryCards } from "./SummaryCards";

const noSubscribe = () => () => {};

export function CalendarView() {
  // "Today" only exists in the browser (Bangkok date); null during server prerender.
  const today = useSyncExternalStore(noSubscribe, () => bangkokToday(), () => null);
  if (!today) return <p className="text-sm text-muted">กำลังโหลด…</p>;
  return <Calendar today={today} />;
}

function Calendar({ today }: { today: string }) {
  const [month, setMonth] = useState<Month>(() => monthOf(today));
  const [picked, setPicked] = useState<string | null>(null);
  const [filters, setFilters] = useState<ReadonlySet<Filter>>(() => new Set(FILTERS));

  const range = monthRange(month);
  const isCurrentMonth = sameMonth(month, monthOf(today));
  const selected =
    picked && sameMonth(monthOf(picked), month) ? picked : isCurrentMonth ? today : range.from;

  const quotes = useApi<QuotesResponse>("/api/quotes");
  const calendar = useApi<CalendarResponse>(`/api/calendar?from=${range.from}&to=${range.to}`);
  const income = useApi<IncomeResponse>(`/api/income/monthly?year=${month.year}`);
  const settings = useApi<SettingsResponse>("/api/settings");
  const earnings = useApi<UpcomingEarnings[]>("/api/earnings/upcoming");

  const days = useMemo(
    () => new Map<string, CalendarDay>((calendar.data?.days ?? []).map((d) => [d.date, d])),
    [calendar.data],
  );
  const payments = useMemo(() => {
    const map = new Map<string, IncomePayment>();
    for (const m of income.data?.months ?? []) {
      for (const p of m.payments) map.set(`${p.ticker}|${p.pay_date}`, p);
    }
    return map;
  }, [income.data]);
  const taxPct = income.data ? formatDecimal(shiftDecimal(income.data.withholding_rate, 2), 0) : null;

  const toggle = (f: Filter) =>
    setFilters((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });

  const go = (delta: number) => {
    setMonth((m) => addMonths(m, delta));
    setPicked(null);
  };

  const period = calendar.data?.period;
  const error = calendar.error ?? quotes.error ?? income.error;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold sm:text-4xl">{formatMonthYear(month.year, month.month)}</h1>
            <div className="flex items-center gap-1">
              <NavButton label="เดือนก่อน" onClick={() => go(-1)}>
                ‹
              </NavButton>
              <NavButton label="เดือนถัดไป" onClick={() => go(1)}>
                ›
              </NavButton>
              {!isCurrentMonth && (
                <button
                  type="button"
                  onClick={() => {
                    setMonth(monthOf(today));
                    setPicked(null);
                  }}
                  className="ml-1 rounded-full border border-line-strong px-3 py-1 text-sm hover:bg-surface-2"
                >
                  วันนี้
                </button>
              )}
            </div>
          </div>
          <p className="mt-2 text-muted">
            {period && (
              <>
                พอร์ต{isCurrentMonth ? "เดือนนี้" : "ทั้งเดือน"}{" "}
                <span className={`num font-semibold ${DIR_TEXT[direction(period.change_pct)]}`}>
                  {arrow(direction(period.change_pct))} {formatPct(period.change_pct)}
                </span>{" "}
                ·{" "}
              </>
            )}
            ทุกอย่างที่เกิดกับหุ้นในพอร์ต · เวลาไทย
          </p>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="แสดงเหตุการณ์">
          {FILTERS.map((f) => {
            const on = filters.has(f);
            return (
              <button
                key={f}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(f)}
                className={`flex items-center gap-2 rounded-full border px-4 py-2 font-medium transition-colors ${
                  on ? "border-ink bg-surface text-ink" : "border-line bg-surface-2 text-muted line-through"
                }`}
              >
                <span className={`size-2.5 rounded-full ${FILTER_META[f].dot} ${on ? "" : "opacity-40"}`} aria-hidden />
                {FILTER_META[f].label}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-down">
          โหลดข้อมูลไม่สำเร็จ: {error.message}
        </p>
      )}

      <SummaryCards
        quotes={quotes.data}
        calendar={calendar.data}
        income={income.data}
        earnings={earnings.data}
        month={month.month}
        isCurrentMonth={isCurrentMonth}
      />

      <PriceStrip quotes={quotes.data} />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <MonthGrid
          month={month}
          days={days}
          loading={calendar.loading}
          filters={filters}
          today={today}
          selected={selected}
          onSelect={setPicked}
        />
        <DayPanel
          iso={selected}
          day={days.get(selected)}
          payments={payments}
          taxPct={taxPct}
          bigMovePct={settings.data?.big_move_threshold_pct ?? null}
        />
      </div>
    </div>
  );
}

function NavButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-9 place-items-center rounded-full border border-line-strong text-xl leading-none hover:bg-surface-2"
    >
      {children}
    </button>
  );
}
