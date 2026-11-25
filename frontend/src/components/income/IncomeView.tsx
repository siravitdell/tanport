"use client";

import { useState, useSyncExternalStore } from "react";

import type { IncomeResponse } from "@/lib/api";
import { bangkokToday } from "@/lib/calendar";
import { formatDecimal, formatThb, shiftDecimal } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import { HoldingsIncomeTable } from "./HoldingsIncomeTable";
import { IncomeChart } from "./IncomeChart";

const noSubscribe = () => () => {};

export function IncomeView() {
  // The current year comes from the browser clock (Bangkok); null during server prerender.
  const today = useSyncExternalStore(noSubscribe, () => bangkokToday(), () => null);
  if (!today) return <p className="text-sm text-muted">กำลังโหลด…</p>;
  return <Income thisYear={Number(today.slice(0, 4))} />;
}

function Income({ thisYear }: { thisYear: number }) {
  const [year, setYear] = useState(thisYear);
  const { data: income, error, loading } = useApi<IncomeResponse>(`/api/income/monthly?year=${year}`);

  const ratePct = income ? formatDecimal(shiftDecimal(income.withholding_rate, 2), 0) : null;
  const w8ben = ratePct === "15" ? " (W-8BEN)" : ratePct === "30" ? " (ไม่มี W-8BEN)" : "";

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold sm:text-4xl">
            รายได้ปันผล <span className="num">{year}</span>
          </h1>
          <div className="flex items-center gap-1">
            <YearButton label="ปีก่อน" onClick={() => setYear((y) => y - 1)}>
              ‹
            </YearButton>
            <YearButton label="ปีถัดไป" onClick={() => setYear((y) => y + 1)}>
              ›
            </YearButton>
            {year !== thisYear && (
              <button
                type="button"
                onClick={() => setYear(thisYear)}
                className="ml-1 rounded-full border border-line-strong px-3 py-1 text-sm hover:bg-surface-2"
              >
                ปีนี้
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 text-muted">
          ยอดสุทธิเป็นบาท หลังหักภาษี ณ ที่จ่ายของสหรัฐฯ {ratePct ?? "…"}%{w8ben} · เรท USD/THB ของวันจ่าย
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-down">
          โหลดข้อมูลไม่สำเร็จ: {error.message}
        </p>
      )}

      {!income || loading ? (
        !error && <p className="text-sm text-muted">กำลังโหลด…</p>
      ) : (
        <>
          <Cards income={income} ratePct={ratePct ?? ""} />
          <IncomeChart income={income} />
          <HoldingsIncomeTable income={income} />
        </>
      )}
    </div>
  );
}

function Cards({ income, ratePct }: { income: IncomeResponse; ratePct: string }) {
  const t = income.totals;
  const card = "rounded-2xl border border-line bg-surface p-6";
  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="สรุปทั้งปี">
      <div className={card}>
        <p className="text-sm text-muted">รวมทั้งปี (สุทธิ)</p>
        <p className="num mt-3 text-4xl font-semibold text-pay-ink">{formatThb(t.net_thb)}</p>
        <p className="mt-2 text-sm text-muted">
          เข้าแล้ว <span className="num">{formatThb(t.received_thb)}</span> + รอเข้า{" "}
          <span className="num">{formatThb(t.upcoming_thb)}</span>
        </p>
      </div>
      <div className={card}>
        <p className="text-sm text-muted">เฉลี่ยต่อเดือน</p>
        <p className="num mt-3 text-4xl font-semibold">{formatThb(t.monthly_avg_thb)}</p>
        <p className="mt-2 text-sm text-muted">passive income ต่อเดือนโดยเฉลี่ย</p>
      </div>
      <div className={card}>
        <p className="text-sm text-muted">Yield on cost ทั้งพอร์ต</p>
        <p className="num mt-3 text-4xl font-semibold">
          {t.yield_on_cost_pct ? `${formatDecimal(t.yield_on_cost_pct, 2)}%` : "–"}
        </p>
        <p className="mt-2 text-sm text-muted">ปันผลสุทธิ ÷ ต้นทุนที่ซื้อจริง</p>
      </div>
      <div className={card}>
        <p className="text-sm text-muted">ภาษีที่ถูกหักไป</p>
        <p className="num mt-3 text-4xl font-semibold text-macro-ink">{formatThb(t.tax_thb)}</p>
        <p className="mt-2 text-sm text-muted">
          {ratePct}% ของยอดก่อนภาษี <span className="num">{formatThb(t.gross_thb)}</span>
        </p>
      </div>
    </section>
  );
}

function YearButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
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
