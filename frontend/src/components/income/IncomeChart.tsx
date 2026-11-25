import type { IncomeResponse } from "@/lib/api";
import { formatShortDate, formatShortMonth } from "@/lib/dates";
import { formatDecimal, formatThb } from "@/lib/format";
import { concentration, isPositive, monthBars } from "@/lib/income";

const PLOT_H = 240; // px, tallest bar
const LABEL_H = 28; // px, room for the value above it

/**
 * Monthly net THB: received = solid, still to come (declared or estimated) = dashed outline.
 * A month that is part received, part upcoming stacks the two with a 2px gap.
 */
export function IncomeChart({ income }: { income: IncomeResponse }) {
  const bars = monthBars(income.months);
  const note = concentration(income.months);
  const months = new Map(income.months.map((m) => [m.month, m]));

  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-7" aria-labelledby="income-chart">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="income-chart" className="text-lg font-bold">
          เงินปันผลเข้ารายเดือน
        </h2>
        <div className="flex items-center gap-4 text-sm text-ink-2">
          <span className="flex items-center gap-1.5">
            <span className="size-3 rounded-[3px] bg-pay-ink" aria-hidden /> เงินเข้าแล้ว
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-3 rounded-[3px] border-[1.5px] border-dashed border-pay-ink bg-pay-bg" aria-hidden />
            รอเข้า (รวมประมาณการ)
          </span>
        </div>
      </div>

      {/* chart: one column per month; hover/focus a column for its payments */}
      <div className="mt-8">
        <div className="grid grid-cols-12 gap-1 border-b border-line-strong sm:gap-3" aria-hidden>
          {bars.map((bar, i) => {
            const payments = months.get(bar.month)?.payments ?? [];
            const has = isPositive(bar.total);
            // keep the tooltip on screen at both ends of the year
            const tipX = i < 3 ? "left-0" : i > 8 ? "right-0" : "left-1/2 -translate-x-1/2";
            return (
              <div
                key={bar.month}
                tabIndex={has ? 0 : -1}
                className="group relative flex flex-col items-center justify-end rounded-t-md outline-none focus-visible:ring-2 focus-visible:ring-ink"
                style={{ height: PLOT_H + LABEL_H }}
              >
                <span
                  className={`num mb-1.5 hidden text-xs font-semibold sm:block lg:text-sm ${has ? "text-ink" : "text-muted"}`}
                >
                  {formatDecimal(bar.total, 0)}
                </span>
                <div className="flex w-full max-w-[72px] flex-col justify-end gap-0.5">
                  {bar.upcomingRatio > 0 && (
                    <div
                      className="w-full rounded-t-[4px] border-[1.5px] border-dashed border-pay-ink bg-pay-bg"
                      style={{ height: Math.max(3, bar.upcomingRatio * PLOT_H) }}
                    />
                  )}
                  {bar.receivedRatio > 0 && (
                    <div
                      className={`w-full bg-pay-ink ${bar.upcomingRatio > 0 ? "" : "rounded-t-[4px]"}`}
                      style={{ height: Math.max(3, bar.receivedRatio * PLOT_H) }}
                    />
                  )}
                  {!has && <div className="h-[3px] w-full rounded-t-[2px] bg-line-strong" />}
                </div>

                {payments.length > 0 && (
                  <div
                    className={`pointer-events-none absolute top-0 z-10 hidden w-60 -translate-y-full rounded-xl border border-line-strong bg-surface p-3 text-left shadow-lg group-hover:block group-focus:block ${tipX}`}
                  >
                    <p className="mb-1.5 text-sm font-semibold">
                      {formatShortMonth(bar.month)} · <span className="num">{formatThb(bar.total)}</span>
                    </p>
                    <ul className="space-y-1 text-xs text-ink-2">
                      {payments.map((p) => (
                        <li key={`${p.ticker}-${p.pay_date}`} className="flex justify-between gap-2">
                          <span>
                            {p.ticker} · {formatShortDate(p.pay_date)}
                            {p.is_estimate ? " · ประมาณการ" : p.status === "upcoming" ? " · รอเข้า" : ""}
                          </span>
                          <span className="num">{p.net_thb ? formatThb(p.net_thb) : "ไม่มีเรท"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-12 gap-1 pt-2 text-center text-[10px] text-muted sm:gap-3 sm:text-sm" aria-hidden>
          {bars.map((bar) => (
            <span key={bar.month}>{formatShortMonth(bar.month)}</span>
          ))}
        </div>
      </div>

      {/* the same data as a table, for screen readers */}
      <table className="sr-only">
        <caption>เงินปันผลสุทธิรายเดือน (บาท)</caption>
        <thead>
          <tr>
            <th>เดือน</th>
            <th>เข้าแล้ว</th>
            <th>รอเข้า</th>
          </tr>
        </thead>
        <tbody>
          {bars.map((bar) => (
            <tr key={bar.month}>
              <td>{formatShortMonth(bar.month)}</td>
              <td>{formatThb(bar.received)}</td>
              <td>{formatThb(bar.upcoming)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {note && (
        <p className="mt-6 flex gap-3 rounded-xl bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <InfoIcon />
          <span>
            เงินเข้ากระจุกอยู่ {note.topMonths.length} เดือน ({note.topMonths.map(formatShortMonth).join(" ")}) คิดเป็น{" "}
            <strong className="num text-ink">{note.sharePct}%</strong> ของทั้งปี
            {note.emptyMonths.length > 0 && (
              <> · {note.emptyMonths.map(formatShortMonth).join(" ")} ไม่มีเงินเข้าเลย</>
            )}
          </span>
        </p>
      )}

      {income.missing_fx.length > 0 && (
        <p className="mt-3 text-sm text-down">
          ยังไม่มีเรท USD/THB ของวันจ่าย {income.missing_fx.map(formatShortDate).join(", ")} จึงยังไม่รวมในยอดบาท
        </p>
      )}
    </section>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" className="mt-0.5 size-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16.5v.5" strokeLinecap="round" />
    </svg>
  );
}
