"use client";

import { useState } from "react";

import { ApiError, type Trade, api } from "@/lib/api";
import { formatDate, formatShortDate } from "@/lib/dates";
import { formatDecimal, formatThbSigned, formatUsd } from "@/lib/format";
import { tradeErrorText } from "@/lib/trade-errors";

const th = "px-1.5 py-3 font-medium sm:px-2.5";
const td = "px-1.5 py-3 sm:px-2.5";
const wide = "hidden sm:table-cell"; // phones: date, ticker (+ side, shares × price), amount

export function TradeHistory({ trades, onChanged }: { trades: Trade[]; onChanged: () => void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(t: Trade) {
    const label = `${t.side === "buy" ? "ซื้อ" : "ขาย"} ${t.ticker} ${t.shares} หุ้น วันที่ ${formatDate(t.trade_date)}`;
    if (!window.confirm(`ลบรายการ ${label}?`)) return;
    setBusy(t.id);
    setError(null);
    try {
      await api.deleteTrade(t.id);
      onChanged();
    } catch (err) {
      setError(tradeErrorText(err instanceof ApiError ? err : null, "delete"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-labelledby="history">
      <h2 id="history" className="text-lg font-bold">
        ประวัติรายการ
      </h2>
      {error && (
        <p role="alert" className="mt-3 text-sm text-down">
          {error}
        </p>
      )}
      {trades.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">ยังไม่มีรายการ</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left sm:min-w-[680px]">
            <thead>
              <tr className="border-b border-line-strong text-sm text-muted">
                <th className={th}>วันที่</th>
                <th className={`${th} ${wide}`}>ประเภท</th>
                <th className={th}>หุ้น</th>
                <th className={`${th} ${wide} text-right`}>จำนวน</th>
                <th className={`${th} ${wide} text-right`}>ราคา</th>
                <th className={`${th} ${wide} text-right`}>เรท ฿/$</th>
                <th className={`${th} text-right`}>ยอดเงิน</th>
                <th className={th}>
                  <span className="sr-only">ลบ</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-line">
                  <td className={`${td} whitespace-nowrap`}>
                    <span className="sm:hidden">{formatShortDate(t.trade_date)}</span>
                    <span className="hidden sm:inline">{formatDate(t.trade_date)}</span>
                  </td>
                  <td className={`${td} ${wide}`}>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        t.side === "buy" ? "bg-pay-bg text-pay-ink" : "border border-down text-down"
                      }`}
                    >
                      {t.side === "buy" ? "ซื้อ" : "ขาย"}
                    </span>
                  </td>
                  <td className={`${td} font-bold`}>
                    {t.ticker}
                    <span className="block text-xs font-normal text-muted sm:hidden">
                      <span className={t.side === "buy" ? "text-pay-ink" : "text-down"}>
                        {t.side === "buy" ? "ซื้อ" : "ขาย"}
                      </span>{" "}
                      <span className="num">
                        {t.shares} × {formatUsd(t.price_usd)}
                      </span>
                    </span>
                  </td>
                  <td className={`${td} ${wide} num text-right`}>{t.shares}</td>
                  <td className={`${td} ${wide} num text-right`}>
                    {formatUsd(t.price_usd)}
                    {t.fee_usd !== "0" && (
                      <span className="block text-xs text-muted">ค่าธรรมเนียม {formatUsd(t.fee_usd)}</span>
                    )}
                  </td>
                  <td className={`${td} ${wide} num text-right text-muted`}>{formatDecimal(t.usd_thb, 2)}</td>
                  <td className={`${td} num whitespace-nowrap text-right font-semibold`}>{formatThbSigned(t.cash_thb)}</td>
                  <td className={`${td} text-right`}>
                    <button
                      type="button"
                      onClick={() => void remove(t)}
                      disabled={busy === t.id}
                      aria-label={`ลบรายการ ${t.ticker} ${formatDate(t.trade_date)}`}
                      title="ลบรายการ"
                      className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-down disabled:opacity-50"
                    >
                      <TrashIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
