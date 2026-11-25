import type { CalendarDay, CalendarEvent, IncomePayment } from "@/lib/api";
import { chipFor, isWeekend } from "@/lib/calendar";
import { formatLongDate, formatShortDate } from "@/lib/dates";
import { arrow, direction, formatDecimal, formatPct, formatThb, formatThbSigned, formatUsd } from "@/lib/format";

import { CHIP_CLASS, DIR_TEXT, ESTIMATE_CLASS } from "./styles";

interface Props {
  iso: string;
  day: CalendarDay | undefined;
  /** The user's dividend payments, keyed `${ticker}|${pay_date}`, for net THB amounts. */
  payments: Map<string, IncomePayment>;
  taxPct: string | null;
  bigMovePct: string | null;
}

export function DayPanel({ iso, day, payments, taxPct, bigMovePct }: Props) {
  const events = day?.events ?? [];
  return (
    <aside className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-live="polite">
      <p className="text-sm text-muted">วันที่เลือก</p>
      <h2 className="mt-1 text-2xl font-bold">{formatLongDate(iso)}</h2>

      <DayPortfolio day={day} iso={iso} />

      {events.length === 0 ? (
        <p className="mt-6 text-sm text-muted">{day ? "ไม่มีเหตุการณ์ของหุ้นในพอร์ตวันนี้" : "กำลังโหลด…"}</p>
      ) : (
        <ul className="mt-5 divide-y divide-line">
          {events.map((e) => (
            <EventRow key={e.id} event={e} payments={payments} taxPct={taxPct} />
          ))}
        </ul>
      )}

      {bigMovePct && (
        <p className="mt-6 border-t border-line pt-4 text-xs leading-relaxed text-muted">
          หุ้นที่ขยับเกิน ±{formatDecimal(bigMovePct, 1).replace(/\.0$/, "")}% ในวันเดียวจะขึ้นเป็นรายการบนปฏิทิน ·
          ราคาของแต่ละหุ้นรายวันและข่าวจะเพิ่มในแผงนี้ในเฟสถัดไป
        </p>
      )}
    </aside>
  );
}

function DayPortfolio({ day, iso }: { day: CalendarDay | undefined; iso: string }) {
  const p = day?.status === "ok" ? day.portfolio : null;
  let content: React.ReactNode;
  if (p?.change_pct) {
    const dir = direction(p.change_pct);
    content = (
      <span className={`num ${DIR_TEXT[dir]}`}>
        <span className="text-2xl font-semibold">
          {arrow(dir)} {formatPct(p.change_pct)}
        </span>
        {p.change_thb && <span className="ml-2 text-sm">({formatThbSigned(p.change_thb)})</span>}
      </span>
    );
  } else {
    const text = !day
      ? "…"
      : day.status === "closed"
        ? isWeekend(iso)
          ? "ตลาดปิด (เสาร์–อาทิตย์)"
          : "ตลาดปิด (วันหยุดตลาดสหรัฐฯ)"
        : day.status === "future"
          ? "ยังไม่ถึงวันซื้อขาย"
          : "ยังไม่มีข้อมูล";
    content = <span className="text-muted">{text}</span>;
  }
  return (
    <div className="mt-5 flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-3">
      <span className="font-medium">พอร์ตทั้งวัน</span>
      {content}
    </div>
  );
}

function EventRow({
  event: e,
  payments,
  taxPct,
}: {
  event: CalendarEvent;
  payments: Map<string, IncomePayment>;
  taxPct: string | null;
}) {
  const chip = chipFor(e);
  const { tag, title, detail } = describe(e, payments, taxPct);
  return (
    <li className="flex gap-3 py-3.5">
      <span
        className={`h-fit shrink-0 rounded-md px-2 py-1 text-xs font-semibold ${CHIP_CLASS[chip.kind]} ${
          chip.estimate ? ESTIMATE_CLASS : ""
        }`}
      >
        {tag}
      </span>
      <div className="min-w-0">
        <p className="font-semibold">{title}</p>
        {detail.length > 0 && <p className="mt-0.5 text-sm text-muted">{detail.join(" · ")}</p>}
      </div>
    </li>
  );
}

const s = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);

function describe(
  e: CalendarEvent,
  payments: Map<string, IncomePayment>,
  taxPct: string | null,
): { tag: string; title: string; detail: string[] } {
  const t = e.ticker ?? "";
  const dps = s(e.payload.dps);
  const estimate = e.is_estimate ? "ประมาณการจากการจ่าย 4 ครั้งล่าสุด" : null;

  switch (e.type) {
    case "price_move": {
      const pct = s(e.payload.change_pct);
      const close = s(e.payload.close);
      const dir = pct ? direction(pct) : "flat";
      return {
        tag: `${arrow(dir)} ราคา`,
        title: `${t} ${pct ? formatPct(pct) : ""} ในวันเดียว`,
        detail: close ? [`ปิดที่ ${formatUsd(close)}`] : [],
      };
    }
    case "dividend_pay": {
      const pay = payments.get(`${t}|${e.event_date}`);
      const detail: string[] = [];
      if (pay?.net_thb) {
        detail.push(`สุทธิ ${formatThb(pay.net_thb)}${taxPct ? ` หลังภาษี ${taxPct}%` : ""}`);
        if (pay.usd_thb && pay.fx_rate_date) {
          detail.push(`เรท ${formatDecimal(pay.usd_thb, 2)} (${formatShortDate(pay.fx_rate_date)})`);
        }
      } else if (pay) {
        detail.push("ยังไม่มีเรทแลกเปลี่ยน");
      }
      const ex = s(e.payload.ex_date);
      if (ex) detail.push(`XD ${formatShortDate(ex)}`);
      if (estimate) detail.push(estimate);
      return {
        tag: "เงินเข้า",
        title: `${t} จ่ายปันผล${dps ? ` ${formatUsd(dps, 4).replace(/0{1,2}$/, "")}/หุ้น` : ""}`,
        detail,
      };
    }
    case "ex_dividend": {
      const payDate = s(e.payload.pay_date);
      const detail = ["ต้องถือหุ้นก่อนวันนี้"];
      if (payDate) detail.push(`จ่าย ${formatShortDate(payDate)}`);
      if (estimate) detail.push(estimate);
      return {
        tag: "XD",
        title: `${t} ขึ้นเครื่องหมาย XD${dps ? ` ${formatUsd(dps, 4).replace(/0{1,2}$/, "")}/หุ้น` : ""}`,
        detail,
      };
    }
    case "macro":
      return { tag: "Macro", title: s(e.payload.name) ?? "เหตุการณ์เศรษฐกิจ", detail: [] };
    case "earnings":
      return { tag: "งบ", title: `${t} ประกาศงบ`, detail: [] };
    case "split":
      return { tag: "Split", title: `${t} แตกพาร์`, detail: [] };
    default:
      return { tag: "ข่าว", title: s(e.payload.headline) ?? t, detail: [] };
  }
}
