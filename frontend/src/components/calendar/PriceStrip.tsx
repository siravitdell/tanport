"use client";

import type { PricesResponse, QuotesResponse } from "@/lib/api";
import { sparkPoints } from "@/lib/calendar";
import { formatShortDate } from "@/lib/dates";
import { type Direction, arrow, direction, formatDecimal, formatPct, formatUsd } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { EmptyPortfolio } from "@/components/EmptyPortfolio";

import { DIR_TEXT } from "./styles";

type Holding = QuotesResponse["holdings"][number];

export function PriceStrip({ quotes }: { quotes: QuotesResponse | undefined }) {
  const holdings = [...(quotes?.holdings ?? [])].sort(
    (a, b) => Number(b.weight_pct ?? -1) - Number(a.weight_pct ?? -1), // order only
  );
  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-labelledby="prices-today">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="prices-today" className="text-lg font-bold">
          ราคาวันนี้
        </h2>
        <p className="text-sm text-muted">กราฟเล็ก = 14 วันทำการล่าสุด · สัดส่วนตามพอร์ตจริง</p>
      </div>
      {!quotes ? (
        <p className="py-6 text-center text-sm text-muted">กำลังโหลด…</p>
      ) : holdings.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted"><EmptyPortfolio /></p>
      ) : (
        <div className="grid auto-cols-[minmax(128px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-1">
          {holdings.map((h) => (
            <PriceCard key={h.ticker} holding={h} />
          ))}
        </div>
      )}
    </section>
  );
}

function PriceCard({ holding: h }: { holding: Holding }) {
  const { data } = useApi<PricesResponse>(`/api/prices?ticker=${encodeURIComponent(h.ticker)}&days=14`);
  const dir: Direction = h.change_pct ? direction(h.change_pct) : "flat";
  return (
    <div className="rounded-xl border border-line bg-surface p-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-bold">{h.ticker}</span>
        {h.weight_pct && <span className="num text-xs text-muted">{formatDecimal(h.weight_pct, 1)}%</span>}
      </div>
      {h.status === "ok" && h.price ? (
        <>
          <p className="num mt-2 text-lg font-medium">{formatUsd(h.price)}</p>
          <p className={`num text-sm font-medium ${DIR_TEXT[dir]}`}>
            {arrow(dir)} {h.change_pct ? formatPct(h.change_pct) : ""}
          </p>
        </>
      ) : (
        <>
          <p className="num mt-2 text-lg text-muted">—</p>
          <p className="text-sm text-muted">ยังไม่มีราคา</p>
        </>
      )}
      <Sparkline prices={data} dir={dir} />
    </div>
  );
}

const W = 120;
const H = 34;

function Sparkline({ prices, dir }: { prices: PricesResponse | undefined; dir: Direction }) {
  const points = prices?.points ?? [];
  if (points.length < 2) {
    return (
      <div className="mt-2 flex h-[34px] items-center text-xs text-muted">
        {prices ? "ยังไม่มีราคาย้อนหลัง" : ""}
      </div>
    );
  }
  const first = points[0];
  const last = points[points.length - 1];
  const step = (W - 4) / (points.length - 1);
  const summary =
    first && last
      ? `ราคาปิด ${points.length} วัน: ${formatUsd(first.close)} (${formatShortDate(first.trade_date)}) ถึง ${formatUsd(last.close)} (${formatShortDate(last.trade_date)})`
      : "";
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={`mt-2 h-[34px] w-full ${DIR_TEXT[dir]}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={summary}
    >
      <polyline
        points={sparkPoints(points.map((p) => p.close), W, H)}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      {/* hover: one hit area per close, wider than the line */}
      {points.map((p, i) => (
        <rect key={p.trade_date} x={2 + (i - 0.5) * step} y={0} width={step} height={H} fill="transparent">
          <title>{`${formatShortDate(p.trade_date)} · ${formatUsd(p.close)}`}</title>
        </rect>
      ))}
    </svg>
  );
}
