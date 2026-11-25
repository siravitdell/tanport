import { EmptyPortfolio } from "@/components/EmptyPortfolio";
import type { CalendarResponse, IncomeResponse, QuotesResponse, UpcomingEarnings } from "@/lib/api";
import { formatDate, formatShortDate, formatShortMonth } from "@/lib/dates";
import { earningsTimeText } from "@/lib/earnings";
import {
  addDecimals,
  arrow,
  direction,
  formatDecimal,
  formatPct,
  formatThb,
  formatThbSigned,
  shiftDecimal,
} from "@/lib/format";

interface Props {
  quotes: QuotesResponse | undefined;
  calendar: CalendarResponse | undefined;
  income: IncomeResponse | undefined;
  earnings: UpcomingEarnings[] | undefined;
  month: number;
  isCurrentMonth: boolean;
}

const card = "rounded-2xl border border-line bg-surface p-6";
const label = "text-sm text-muted";

export function SummaryCards({ quotes, calendar, income, earnings, month, isCurrentMonth }: Props) {
  const monthWord = isCurrentMonth ? "เดือนนี้" : `เดือน ${formatShortMonth(month)}`;
  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="สรุป">
      <PortfolioCard quotes={quotes} />
      <DividendCard income={income} month={month} monthWord={monthWord} />
      <XdCard calendar={calendar} monthWord={monthWord} />
      <EarningsCard earnings={earnings} />
    </section>
  );
}

function PortfolioCard({ quotes }: { quotes: QuotesResponse | undefined }) {
  const p = quotes?.portfolio;
  const dir = p ? direction(p.change_pct) : "flat";
  const changeClass = dir === "down" ? "text-hero-down" : dir === "up" ? "text-hero-accent" : "text-hero-muted";
  const when = quotes?.market.is_open
    ? "วันนี้"
    : quotes
      ? `รอบ ${formatShortDate(quotes.market.last_session_date)}`
      : "";
  return (
    <div className="rounded-2xl bg-hero p-6 text-hero-ink">
      <p className="text-sm text-hero-muted">มูลค่าพอร์ตวันนี้</p>
      {p ? (
        <>
          <p className="num mt-3 text-4xl font-semibold">{formatThb(p.value_thb)}</p>
          <p className={`num mt-2 font-medium ${changeClass}`}>
            {arrow(dir)} {formatPct(p.change_pct)} ({formatThbSigned(p.change_thb)})
            {when === "วันนี้" && <span className="font-sans"> วันนี้</span>}
          </p>
          {when !== "วันนี้" && <p className="mt-0.5 text-xs text-hero-muted">ตลาดปิด · ราคา{when}</p>}
          {p.excluded.length > 0 && (
            <p className="mt-1 text-xs text-hero-muted">ไม่รวม {p.excluded.join(", ")} (ยังไม่มีราคา)</p>
          )}
        </>
      ) : (
        <>
          <p className="mt-3 text-3xl font-semibold text-hero-muted">{quotes ? "—" : "…"}</p>
          {quotes && (
            <p className="mt-2 text-sm text-hero-muted">
              {quotes.holdings.length === 0 ? <EmptyPortfolio /> : "ยังไม่มีราคา รอดึงราคารอบถัดไป"}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function DividendCard({
  income,
  month,
  monthWord,
}: {
  income: IncomeResponse | undefined;
  month: number;
  monthWord: string;
}) {
  const m = income?.months.find((x) => x.month === month);
  const payments = m?.payments ?? [];
  const total = m ? addDecimals([m.received_thb, m.upcoming_thb]) : null;
  const taxPct = income ? formatDecimal(shiftDecimal(income.withholding_rate, 2), 0) : "15";
  const estimates = payments.filter((p) => p.is_estimate).length;
  const noFx = payments.filter((p) => p.net_thb === null).length;
  return (
    <div className={card}>
      <p className={label}>
        ปันผลสุทธิ{monthWord} (หลังภาษี {taxPct}%)
      </p>
      <p className="num mt-3 text-4xl font-semibold text-pay-ink">{total ? formatThb(total) : "…"}</p>
      <p className="mt-2 text-sm text-muted">
        {payments.length === 0 && m
          ? "ไม่มีเงินปันผลเข้า"
          : `จาก ${payments.length} รายการเงินเข้า${estimates ? ` (ประมาณการ ${estimates})` : ""}`}
        {noFx > 0 && ` · ${noFx} รายการยังไม่มีเรท`}
      </p>
    </div>
  );
}

function XdCard({ calendar, monthWord }: { calendar: CalendarResponse | undefined; monthWord: string }) {
  const count = calendar?.days.reduce(
    (n, d) => n + d.events.filter((e) => e.type === "ex_dividend").length,
    0,
  );
  return (
    <div className={card}>
      <p className={label}>วัน XD ใน{monthWord}</p>
      <p className="mt-3 text-4xl font-semibold text-xd-ink">
        {count === undefined ? "…" : <><span className="num">{count}</span> ครั้ง</>}
      </p>
      <p className="mt-2 text-sm text-muted">ต้องถือหุ้นก่อนวัน XD ถึงได้ปันผล</p>
    </div>
  );
}

/** The next announcement, and who else reports within three weeks of it. */
function EarningsCard({ earnings }: { earnings: UpcomingEarnings[] | undefined }) {
  const first = earnings?.[0];
  const soon = first
    ? earnings.filter((e) => Date.parse(e.date) - Date.parse(first.date) <= 21 * 86_400_000)
    : [];
  return (
    <div className="rounded-2xl border border-line bg-surface p-6">
      <p className="text-sm text-muted">ประกาศงบรอบถัดไป</p>
      {!earnings ? (
        <p className="mt-3 text-3xl font-bold text-muted">…</p>
      ) : !first ? (
        <>
          <p className="mt-3 text-3xl font-bold text-muted">—</p>
          <p className="mt-2 text-sm text-muted">ไม่มีกำหนดใน 90 วันข้างหน้า</p>
        </>
      ) : (
        <>
          <p className="mt-3 text-3xl font-bold text-earn-ink">{formatDate(first.date)}</p>
          <p className="mt-2 text-sm text-muted">
            {soon.map((e) => `${e.ticker} ${formatShortDate(e.date)}`).join(" · ")}
          </p>
          <p className="mt-1 text-xs text-muted">
            {first.ticker}: {earningsTimeText(first.hour, first.time_utc, first.date)}
          </p>
        </>
      )}
    </div>
  );
}
