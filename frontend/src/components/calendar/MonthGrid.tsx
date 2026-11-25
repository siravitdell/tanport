import type { CalendarDay } from "@/lib/api";
import {
  type Filter,
  type GridDay,
  type Month,
  cellChips,
  chipFor,
  isWeekend,
  monthGrid,
  visibleEvents,
} from "@/lib/calendar";
import { WEEKDAYS_MON_FIRST, formatLongDate } from "@/lib/dates";
import { direction, formatPct } from "@/lib/format";

import { CHIP_CLASS, CHIP_DOT, DIR_TEXT, ESTIMATE_CLASS } from "./styles";

interface Props {
  month: Month;
  days: Map<string, CalendarDay>;
  loading: boolean;
  filters: ReadonlySet<Filter>;
  today: string;
  selected: string;
  onSelect: (iso: string) => void;
}

export function MonthGrid({ month, days, loading, filters, today, selected, onSelect }: Props) {
  const weeks = monthGrid(month);
  return (
    <section className="rounded-2xl border border-line bg-surface p-3 sm:p-5" aria-label="ปฏิทินรายเดือน">
      <div className="grid grid-cols-7 gap-1.5 sm:gap-2" aria-busy={loading}>
        <div className="contents">
          {WEEKDAYS_MON_FIRST.map((d) => (
            <div key={d} aria-hidden className="px-2 pb-2 text-sm font-medium text-muted">
              {d}
            </div>
          ))}
        </div>
        {weeks.map((week) => (
          <div key={week[0]?.iso} className="contents">
            {week.map((cell) => (
              <DayCell
                key={cell.iso}
                cell={cell}
                day={cell.inMonth ? days.get(cell.iso) : undefined}
                filters={filters}
                isToday={cell.iso === today}
                isSelected={cell.iso === selected}
                onSelect={onSelect}
              />
            ))}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">
        % มุมขวาบน = พอร์ตทั้งวัน (ตามวันซื้อขายของตลาดสหรัฐฯ) · กรอบเส้นประ = ประมาณการ ยังไม่ประกาศ
      </p>
    </section>
  );
}

function DayCell({
  cell,
  day,
  filters,
  isToday,
  isSelected,
  onSelect,
}: {
  cell: GridDay;
  day: CalendarDay | undefined;
  filters: ReadonlySet<Filter>;
  isToday: boolean;
  isSelected: boolean;
  onSelect: (iso: string) => void;
}) {
  if (!cell.inMonth) {
    return (
      <div aria-hidden className="min-h-20 rounded-xl bg-surface-2 p-1.5 sm:min-h-32 sm:p-2.5">
        <span className="num text-sm text-muted">{cell.day}</span>
      </div>
    );
  }

  const events = day ? visibleEvents(day.events, filters) : [];
  const { chips, more } = cellChips(events);
  const pct = day?.status === "ok" ? day.portfolio?.change_pct ?? null : null;
  const dir = pct ? direction(pct) : "flat";

  return (
    <button
      type="button"
      aria-pressed={isSelected}
      aria-label={`${formatLongDate(cell.iso)}${pct ? ` พอร์ต ${formatPct(pct)}` : ""}${events.length ? ` ${events.length} รายการ` : ""}`}
      onClick={() => onSelect(cell.iso)}
      className={`flex min-h-20 min-w-0 flex-col gap-1 rounded-xl border bg-surface p-1.5 text-left transition-colors hover:bg-surface-2 sm:min-h-32 sm:p-2.5 ${
        isSelected ? "border-2 border-ink" : "border-line"
      }`}
    >
      {/* phones: number above the %, wider screens: side by side */}
      <span className="flex flex-col items-start gap-0.5 sm:flex-row sm:items-center sm:justify-between sm:gap-1">
        <span className="flex items-center gap-1">
          <span
            className={`num text-sm font-medium ${
              isToday ? "rounded-full bg-hero px-1 text-hero-ink sm:bg-transparent sm:px-0 sm:text-ink" : ""
            }`}
          >
            {cell.day}
          </span>
          {isToday && (
            <span className="hidden whitespace-nowrap rounded-full bg-hero px-1.5 text-[11px] font-semibold text-hero-ink sm:inline">
              วันนี้
            </span>
          )}
        </span>
        {/* today without a close yet: the badge is enough (the panel says "ยังไม่มีข้อมูล") */}
        {!(isToday && !pct) && (
          <DayStatusText day={day} pct={pct} dir={dir} isWeekendDay={isWeekend(cell.iso)} />
        )}
      </span>

      {/* chips on wider screens, a count on phones */}
      <span className="hidden flex-col gap-1 sm:flex">
        {chips.map((chip, i) => (
          <span
            key={i}
            title={chip.estimate ? `${chip.label} (ประมาณการ)` : chip.label}
            className={`truncate rounded-md px-1 py-0.5 text-[11px] font-medium 2xl:px-1.5 2xl:text-xs ${CHIP_CLASS[chip.kind]} ${
              chip.estimate ? ESTIMATE_CLASS : ""
            }`}
          >
            {chip.label}
          </span>
        ))}
        {more > 0 && <span className="px-1 text-xs text-muted">+{more} รายการ</span>}
      </span>
      {/* phones: one dot per event (the day panel lists them) */}
      {events.length > 0 && (
        <span className="mt-auto flex flex-wrap gap-0.5 sm:hidden" aria-hidden>
          {events.slice(0, 6).map((e, i) => (
            <span key={i} className={`size-1.5 rounded-full ${CHIP_DOT[chipFor(e).kind]}`} />
          ))}
        </span>
      )}
    </button>
  );
}

/** Never 0 % for a day without data: closed / no data / nothing for future days. */
function DayStatusText({
  day,
  pct,
  dir,
  isWeekendDay,
}: {
  day: CalendarDay | undefined;
  pct: string | null;
  dir: "up" | "down" | "flat";
  isWeekendDay: boolean;
}) {
  if (pct) {
    return (
      <span className={`num whitespace-nowrap font-medium ${DIR_TEXT[dir]}`}>
        <span className="text-[10px] sm:hidden">{formatPct(pct, 1)}</span>
        <span className="hidden text-xs sm:inline lg:text-sm">{formatPct(pct)}</span>
      </span>
    );
  }
  if (!day) return null;
  if (day.status === "closed" && !isWeekendDay) {
    return <span className="whitespace-nowrap text-[10px] text-muted sm:text-[11px]">ตลาดปิด</span>;
  }
  if (day.status === "no_data" || (day.status === "ok" && !pct)) {
    return (
      <span className="whitespace-nowrap text-[11px] text-muted" title="ยังไม่มีข้อมูล">
        <span className="hidden lg:inline">รอข้อมูล</span>
        <span className="lg:hidden">–</span>
      </span>
    );
  }
  return null;
}
