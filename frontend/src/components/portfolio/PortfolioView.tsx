"use client";

import { useSyncExternalStore } from "react";

import type { PortfolioResponse, Trade } from "@/lib/api";
import { bangkokToday } from "@/lib/calendar";
import { direction, formatPct, formatThb, formatThbSigned, formatUsd } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import { DIR_TEXT } from "@/components/calendar/styles";

import { CsvImport } from "./CsvImport";
import { HoldingsTable } from "./HoldingsTable";
import { TradeForm } from "./TradeForm";
import { TradeHistory } from "./TradeHistory";

const noSubscribe = () => () => {};

export function PortfolioView() {
  const today = useSyncExternalStore(noSubscribe, () => bangkokToday(), () => null);
  const portfolio = useApi<PortfolioResponse>("/api/portfolio");
  const trades = useApi<Trade[]>("/api/trades");
  const reload = () => {
    portfolio.reload();
    trades.reload();
  };
  const error = portfolio.error ?? trades.error;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold sm:text-4xl">พอร์ตของฉัน</h1>
        <p className="mt-2 text-muted">
          บันทึกทุกครั้งที่ซื้อหรือขาย ระบบคำนวณจำนวนหุ้น ต้นทุนเฉลี่ย และกำไร/ขาดทุนให้อัตโนมัติ
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-down">
          โหลดข้อมูลไม่สำเร็จ: {error.message}
        </p>
      )}

      <Cards data={portfolio.data} />

      {/* minmax(0, …): wide tables scroll inside their card instead of widening the page */}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
        <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 sm:p-6">
          {today ? (
            <TradeForm today={today} positions={portfolio.data?.positions ?? []} onSaved={reload} />
          ) : (
            <p className="text-sm text-muted">กำลังโหลด…</p>
          )}
          <div className="border-t border-line pt-4">
            <CsvImport onImported={reload} />
          </div>
        </div>
        {portfolio.data ? (
          <HoldingsTable positions={portfolio.data.positions} />
        ) : (
          <p className="text-sm text-muted">กำลังโหลด…</p>
        )}
      </div>

      {trades.data && <TradeHistory trades={trades.data} onChanged={reload} />}
    </div>
  );
}

function Cards({ data }: { data: PortfolioResponse | undefined }) {
  const t = data?.totals;
  const card = "rounded-2xl border border-line bg-surface p-6";
  const signed = (v: string) => (
    <span className={DIR_TEXT[direction(v, 0)]}>{formatThbSigned(v)}</span>
  );
  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="สรุปพอร์ต">
      <div className="rounded-2xl bg-hero p-6 text-hero-ink">
        <p className="text-sm text-hero-muted">มูลค่าพอร์ตตอนนี้</p>
        <p className="num mt-3 text-4xl font-semibold">{t ? formatThb(t.value_thb) : data ? "฿0" : "…"}</p>
        <p className="num mt-2 text-sm text-hero-muted">
          {t ? formatUsd(t.value_usd) : ""}
          {t && t.unpriced.length > 0 && (
            <span className="font-sans"> · ไม่รวม {t.unpriced.join(", ")} (ยังไม่มีราคา)</span>
          )}
        </p>
      </div>
      <div className={card}>
        <p className="text-sm text-muted">ต้นทุนรวม</p>
        <p className="num mt-3 text-4xl font-semibold">{t ? formatThb(t.cost_thb) : "–"}</p>
        <p className="mt-2 text-sm text-muted">
          {t ? (
            <>
              จาก <span className="num">{t.trades}</span> รายการ
            </>
          ) : (
            "ยังไม่มีรายการ"
          )}
        </p>
      </div>
      <div className={card}>
        <p className="text-sm text-muted">กำไร/ขาดทุน (ยังไม่ขาย)</p>
        <p className="num mt-3 text-4xl font-semibold">
          {t ? (
            <>
              {signed(t.unrealized_thb)}
              {t.unrealized_pct && (
                <span className={`ml-2 text-base ${DIR_TEXT[direction(t.unrealized_pct)]}`}>
                  ({formatPct(t.unrealized_pct)})
                </span>
              )}
            </>
          ) : (
            "–"
          )}
        </p>
        {t && (
          <p className="mt-2 text-sm text-muted">
            จากราคาหุ้น <span className="num font-semibold">{signed(t.price_pl_thb)}</span> · จากค่าเงิน{" "}
            <span className="num font-semibold">{signed(t.fx_pl_thb)}</span>
          </p>
        )}
      </div>
      <div className={card}>
        <p className="text-sm text-muted">กำไร/ขาดทุนที่ขายแล้ว</p>
        <p className="num mt-3 text-4xl font-semibold">{t ? signed(t.realized_thb) : "–"}</p>
        <p className="mt-2 text-sm text-muted">คิดแบบต้นทุนเฉลี่ย (average cost)</p>
      </div>
    </section>
  );
}
