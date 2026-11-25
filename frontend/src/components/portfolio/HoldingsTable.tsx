import type { Position } from "@/lib/api";
import { direction, formatDecimal, formatPct, formatThb, formatThbSigned, formatUsd } from "@/lib/format";

import { DIR_TEXT } from "@/components/calendar/styles";

const th = "px-2.5 py-3 font-medium";
const td = "px-2.5 py-3.5";
const wide = "hidden sm:table-cell"; // secondary columns: phones get a compact table, no sideways scroll

export function HoldingsTable({ positions }: { positions: Position[] }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-labelledby="held">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="held" className="text-lg font-bold">
          หุ้นที่ถืออยู่
        </h2>
        <p className="text-sm text-muted">คำนวณจากรายการซื้อขายทั้งหมด</p>
      </div>
      {positions.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">ยังไม่มีหุ้น เริ่มจากบันทึกการซื้อ</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left sm:min-w-[640px]">
            <thead>
              <tr className="border-b border-line-strong text-sm text-muted">
                <th className={th}>หุ้น</th>
                <th className={`${th} text-right`}>จำนวน</th>
                <th className={`${th} ${wide} text-right`}>ต้นทุนเฉลี่ย</th>
                <th className={`${th} ${wide} text-right`}>ราคาล่าสุด</th>
                <th className={`${th} text-right`}>มูลค่า</th>
                <th className={`${th} text-right`}>กำไร/ขาดทุน</th>
                <th className={`${th} ${wide}`}>สัดส่วน</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const dir = p.unrealized_thb ? direction(p.unrealized_thb, 0) : "flat";
                return (
                  <tr key={p.ticker} className="border-b border-line">
                    <td className={`${td} font-bold`}>{p.ticker}</td>
                    <td className={`${td} num text-right`}>{p.shares}</td>
                    <td className={`${td} ${wide} num text-right`}>{formatUsd(p.avg_cost_usd)}</td>
                    <td className={`${td} ${wide} num text-right`}>
                      {p.price_usd ? (
                        <span title={p.price_source === "close" ? "ราคาปิดล่าสุด" : "ราคาล่าสุด"}>
                          {formatUsd(p.price_usd)}
                        </span>
                      ) : (
                        <span className="text-muted">ยังไม่มีราคา</span>
                      )}
                    </td>
                    <td className={`${td} num text-right`}>{p.value_thb ? formatThb(p.value_thb) : "–"}</td>
                    <td className={`${td} num text-right leading-tight ${DIR_TEXT[dir]}`}>
                      {p.unrealized_thb ? (
                        <>
                          <span className="block font-semibold">{formatThbSigned(p.unrealized_thb)}</span>
                          {p.unrealized_pct && <span className="text-xs">{formatPct(p.unrealized_pct)}</span>}
                        </>
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className={`${td} ${wide}`}>
                      {p.weight_pct ? (
                        <span className="flex items-center gap-2">
                          <span className="h-1.5 w-20 overflow-hidden rounded-full bg-line" aria-hidden>
                            <span
                              className="block h-full rounded-full bg-ink-2"
                              style={{ width: `${Math.min(100, Number(p.weight_pct))}%` }}
                            />
                          </span>
                          <span className="num text-xs text-muted">{formatDecimal(p.weight_pct, 1)}%</span>
                        </span>
                      ) : (
                        <span className="text-xs text-muted">–</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
