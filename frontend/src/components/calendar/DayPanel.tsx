"use client";

import { useState } from "react";

import type { CalendarDay, CalendarEvent, DayNewsItem, DayResponse, IncomePayment } from "@/lib/api";
import { chipFor, isWeekend } from "@/lib/calendar";
import { formatLongDate, formatShortDate, formatTime } from "@/lib/dates";
import { earningsTimeText, epsText, fiscalLabel } from "@/lib/earnings";
import { arrow, direction, formatDecimal, formatPct, formatThb, formatThbSigned, formatUsd } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import { CHIP_CLASS, DIR_TEXT, ESTIMATE_CLASS } from "./styles";

interface Props {
  iso: string;
  /** The calendar's copy of the day: shown until the day's own detail has loaded. */
  day: CalendarDay | undefined;
  /** The user's dividend payments, keyed `${ticker}|${pay_date}`, for net THB amounts. */
  payments: Map<string, IncomePayment>;
  taxPct: string | null;
  bigMovePct: string | null;
}

const NEWS_SHOWN = 3;

export function DayPanel({ iso, day, payments, taxPct, bigMovePct }: Props) {
  const { data: detail } = useApi<DayResponse>(`/api/day/${iso}?news_per_ticker=10`);
  const events = detail?.events ?? day?.events ?? [];
  const newsTickers = new Set(detail?.news.map((n) => n.ticker));
  return (
    <aside className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-live="polite">
      <p className="text-sm text-muted">วันที่เลือก</p>
      <h2 className="mt-1 text-2xl font-bold">{formatLongDate(iso)}</h2>

      <DayPortfolio day={day} detail={detail} iso={iso} />
      {detail && <HoldingMoves detail={detail} />}

      {events.length === 0 ? (
        <p className="mt-6 text-sm text-muted">{day || detail ? "ไม่มีเหตุการณ์ของหุ้นในพอร์ตวันนี้" : "กำลังโหลด…"}</p>
      ) : (
        <ul className="mt-5 divide-y divide-line">
          {events.map((e) => (
            <EventRow
              key={e.id}
              event={e}
              payments={payments}
              taxPct={taxPct}
              newsAnchor={e.type === "price_move" && e.ticker && newsTickers.has(e.ticker) ? e.ticker : null}
            />
          ))}
        </ul>
      )}

      {detail && detail.news.length > 0 && (
        <NewsList
          news={detail.news}
          // the likely-cause news of a big move is open; the rest one line each
          openFirst={new Set(events.filter((e) => e.type === "price_move" && e.ticker).map((e) => e.ticker ?? ""))}
        />
      )}

      {bigMovePct && (
        <p className="mt-6 border-t border-line pt-4 text-xs leading-relaxed text-muted">
          หุ้นที่ขยับเกิน ±{formatDecimal(bigMovePct, 1).replace(/\.0$/, "")}% ในวันเดียวจะขึ้นเป็นรายการบนปฏิทิน ·
          ข่าวยังเป็นพาดหัวต้นฉบับ (สรุปภาษาไทยและคะแนนความสำคัญจะตามมาภายหลัง)
        </p>
      )}
    </aside>
  );
}

function DayPortfolio({
  day,
  detail,
  iso,
}: {
  day: CalendarDay | undefined;
  detail: DayResponse | undefined;
  iso: string;
}) {
  const change = detail?.portfolio
    ? { pct: detail.portfolio.change_pct, thb: detail.portfolio.change_thb }
    : day?.status === "ok" && day.portfolio?.change_pct
      ? { pct: day.portfolio.change_pct, thb: day.portfolio.change_thb }
      : null;
  const status = detail?.status ?? day?.status;
  let content: React.ReactNode;
  if (change) {
    const dir = direction(change.pct);
    content = (
      <span className={`num flex flex-col items-end whitespace-nowrap ${DIR_TEXT[dir]}`}>
        <span className="text-2xl font-semibold">
          {arrow(dir)} {formatPct(change.pct)}
        </span>
        {change.thb && <span className="text-sm">{formatThbSigned(change.thb)}</span>}
      </span>
    );
  } else {
    const text = !status
      ? "…"
      : status === "closed"
        ? isWeekend(iso)
          ? "ตลาดปิด (เสาร์–อาทิตย์)"
          : "ตลาดปิด (วันหยุดตลาดสหรัฐฯ)"
        : status === "future"
          ? "ยังไม่ถึงวันซื้อขาย"
          : "ยังไม่มีข้อมูล";
    content = <span className="text-muted">{text}</span>;
  }
  return (
    <div className="mt-5 flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-3">
      <span className="whitespace-nowrap font-medium">พอร์ตทั้งวัน</span>
      {content}
    </div>
  );
}

/** Every holding's move that day, biggest first (mockup: 3-column tiles). */
function HoldingMoves({ detail }: { detail: DayResponse }) {
  if (detail.holdings.length === 0 && detail.unpriced.length === 0) return null;
  return (
    <div className="mt-3">
      <ul className="grid grid-cols-3 gap-1.5" aria-label="หุ้นแต่ละตัววันนี้">
        {detail.holdings.map((h) => {
          const dir = direction(h.change_pct);
          return (
            <li
              key={h.ticker}
              className="rounded-lg bg-surface-2 px-2.5 py-2"
              title={`ปิดที่ ${formatUsd(h.close)} · ${formatThbSigned(h.change_thb)}`}
            >
              <span className="block text-sm font-bold">{h.ticker}</span>
              <span className={`num text-xs font-medium ${DIR_TEXT[dir]}`}>
                {arrow(dir)} {formatPct(h.change_pct)}
              </span>
            </li>
          );
        })}
      </ul>
      {detail.unpriced.length > 0 && (
        <p className="mt-1.5 text-xs text-muted">ยังไม่มีราคาปิด: {detail.unpriced.join(", ")}</p>
      )}
    </div>
  );
}

function NewsList({ news, openFirst }: { news: DayResponse["news"]; openFirst: ReadonlySet<string> }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set(openFirst));
  const [more, setMore] = useState<ReadonlySet<string>>(() => new Set());
  const toggle = (set: typeof setOpen, ticker: string) =>
    set((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  return (
    <section className="mt-5 border-t border-line pt-4" aria-label="ข่าววันนี้">
      <h3 className="mb-2 text-sm font-semibold">ข่าววันนี้ของหุ้นในพอร์ต</h3>
      <ul className="divide-y divide-line">
        {news.map((group) => {
          const isOpen = open.has(group.ticker);
          const all = more.has(group.ticker);
          const shown = all ? group.items : group.items.slice(0, NEWS_SHOWN);
          const hidden = group.items.length - shown.length;
          return (
            <li key={group.ticker} id={`news-${group.ticker}`} className="scroll-mt-4 py-2">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => toggle(setOpen, group.ticker)}
                className="flex w-full items-baseline justify-between gap-2 text-left text-sm"
              >
                <span className="font-semibold">
                  <span className="mr-1.5 rounded-md bg-news-bg px-1.5 py-0.5 text-xs text-news-ink">ข่าว</span>
                  {group.ticker}
                </span>
                <span className="text-xs text-muted">
                  {group.total} ข่าววันนี้ {isOpen ? "▾" : "▸"}
                </span>
              </button>
              {isOpen && (
                <>
                  <ul className="mt-2 space-y-2.5">
                    {shown.map((n) => (
                      <NewsRow key={n.id} item={n} />
                    ))}
                  </ul>
                  {(hidden > 0 || group.total > group.items.length) && (
                    <p className="mt-1.5 text-xs text-muted">
                      {hidden > 0 ? (
                        <button type="button" className="underline" onClick={() => toggle(setMore, group.ticker)}>
                          แสดงอีก {hidden} ข่าว
                        </button>
                      ) : (
                        `${group.items.length} ข่าวล่าสุดจาก ${group.total}`
                      )}
                    </p>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
function NewsRow({ item }: { item: DayNewsItem }) {
  return (
    <li className="text-sm">
      <a href={item.url} target="_blank" rel="noopener noreferrer" className="font-medium hover:underline">
        {item.headline}
      </a>
      {item.summary ? (
        <p className="mt-0.5 text-ink-2">{item.summary}</p>
      ) : (
        item.snippet && <p className="mt-0.5 line-clamp-2 text-muted">{item.snippet}</p>
      )}
      <p className="mt-0.5 text-xs text-muted">
        {item.source} · {formatTime(item.published_at)} น.
        {item.importance !== null && ` · ความสำคัญ ${item.importance}/5`}
      </p>
    </li>
  );
}
function EventRow({
  event: e,
  payments,
  taxPct,
  newsAnchor,
}: {
  event: CalendarEvent;
  payments: Map<string, IncomePayment>;
  taxPct: string | null;
  newsAnchor: string | null; // a price move: link to that ticker's news below
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
        {newsAnchor && (
          <a href={`#news-${newsAnchor}`} className="mt-0.5 inline-block text-sm text-ink-2 underline">
            ดูข่าว {newsAnchor} วันนี้ที่อาจเป็นสาเหตุ
          </a>
        )}
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
    case "earnings": {
      const label = fiscalLabel(e.payload.quarter, e.payload.fiscal_year);
      const eps = epsText(s(e.payload.eps_estimate), s(e.payload.eps_actual));
      return {
        tag: "งบ",
        title: `${t} ประกาศงบ${label ? ` ${label}` : ""}`,
        detail: [earningsTimeText(s(e.payload.hour) ?? "unknown", e.event_time_utc, e.event_date), eps].filter(Boolean),
      };
    }
    case "split":
      return { tag: "Split", title: `${t} แตกพาร์`, detail: [] };
    default:
      return { tag: "ข่าว", title: s(e.payload.headline) ?? t, detail: [] };
  }
}
