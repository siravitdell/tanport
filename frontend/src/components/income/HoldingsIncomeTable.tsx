import type { IncomeResponse } from "@/lib/api";
import { formatShortMonth } from "@/lib/dates";
import { formatDecimal, formatThb } from "@/lib/format";

type Row = IncomeResponse["holdings"][number];

/** Net per holding for the year, highest first; non-payers (e.g. AMZN) last. */
export function HoldingsIncomeTable({ income }: { income: IncomeResponse }) {
  const rows = [...income.holdings].sort(
    (a, b) =>
      Number(b.pays_dividend) - Number(a.pays_dividend) ||
      Number(b.net_thb) - Number(a.net_thb) || // ordering only
      a.ticker.localeCompare(b.ticker),
  );
  const months = (r: Row) =>
    !r.pays_dividend
      ? "ไม่จ่ายปันผล"
      : r.pay_months.length
        ? r.pay_months.map(formatShortMonth).join(" ")
        : "ไม่มีในปีนี้";
  const yoc = (r: { yield_on_cost_pct: string | null }) =>
    r.yield_on_cost_pct ? `${formatDecimal(r.yield_on_cost_pct, 2)}%` : "–";

  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-7" aria-labelledby="per-holding">
      <h2 id="per-holding" className="text-lg font-bold">
        ปันผลรายหุ้น
      </h2>
      {rows.length === 0 ? (
        <p className="mt-6 text-sm text-muted">ยังไม่มีหุ้นในพอร์ต</p>
      ) : (
        <div className="mt-4">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line-strong text-sm text-muted">
                <th className="px-2.5 py-3 font-medium">หุ้น</th>
                <th className="hidden px-2.5 py-3 font-medium sm:table-cell">เดือนที่จ่าย</th>
                <th className="px-2.5 py-3 text-right font-medium">ต่อปี (สุทธิ)</th>
                <th className="px-2.5 py-3 text-right font-medium">Yield on cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: Row) => (
                <tr key={r.ticker} className="border-b border-line">
                  <td className="px-2.5 py-3.5 font-bold">
                    {r.ticker}
                    {/* phones: pay months under the ticker instead of their own column */}
                    <span className="block text-xs font-normal text-muted sm:hidden">{months(r)}</span>
                  </td>
                  {r.pays_dividend ? (
                    <>
                      <td className="hidden px-2.5 py-3.5 text-ink-2 sm:table-cell">{months(r)}</td>
                      <td className="num px-2.5 py-3.5 text-right">{formatThb(r.net_thb)}</td>
                      <td className="num px-2.5 py-3.5 text-right">{yoc(r)}</td>
                    </>
                  ) : (
                    <>
                      <td className="hidden px-2.5 py-3.5 text-muted sm:table-cell">ไม่จ่ายปันผล</td>
                      <td className="num px-2.5 py-3.5 text-right text-muted">–</td>
                      <td className="num px-2.5 py-3.5 text-right text-muted">–</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="px-2.5 py-4 font-bold">รวม</td>
                <td className="hidden sm:table-cell" />
                <td className="num px-2.5 py-4 text-right font-semibold text-pay-ink">
                  {formatThb(income.totals.net_thb)}
                </td>
                <td className="num px-2.5 py-4 text-right">{yoc(income.totals)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <p className="mt-4 text-xs text-muted">
        Yield on cost = ปันผลสุทธิ (USD) ÷ ต้นทุนที่ซื้อจริง · คิดจากจำนวนหุ้นที่ถืออยู่ตอนนี้
      </p>
    </section>
  );
}
