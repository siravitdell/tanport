/** Everything is displayed in Thai time, Gregorian years (the mockup shows "ธันวาคม 2026"). */
export const DISPLAY_TZ = "Asia/Bangkok";
const LOCALE = "th-TH-u-ca-gregory-nu-latn";

const timeFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: DISPLAY_TZ,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const shortDateFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: "UTC", // a calendar date (YYYY-MM-DD) has no time zone of its own
  day: "numeric",
  month: "short",
});

const monthYearFmt = new Intl.DateTimeFormat(LOCALE, { timeZone: "UTC", month: "long", year: "numeric" });
const longDateFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: "UTC",
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const utcDate = (isoDate: string) => new Date(`${isoDate}T00:00:00Z`);

const shortMonthFmt = new Intl.DateTimeFormat(LOCALE, { timeZone: "UTC", month: "short" });

/** 12 → "ธ.ค." */
export function formatShortMonth(month: number): string {
  return shortMonthFmt.format(new Date(Date.UTC(2000, month - 1, 1)));
}

/** (2026, 12) → "ธันวาคม 2026" */
export function formatMonthYear(year: number, month: number): string {
  return monthYearFmt.format(new Date(Date.UTC(year, month - 1, 1)));
}

/** "2026-12-16" → "วันพุธที่ 16 ธันวาคม 2026" */
export function formatLongDate(isoDate: string): string {
  const parts = Object.fromEntries(
    longDateFmt.formatToParts(utcDate(isoDate)).map((p) => [p.type, p.value]),
  );
  return `${parts.weekday}ที่ ${parts.day} ${parts.month} ${parts.year}`;
}

export const WEEKDAYS_MON_FIRST = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."];

/** "2026-11-25T21:00:00Z" → "04:00" in Bangkok. */
export function formatTime(isoDateTime: string): string {
  return timeFmt.format(new Date(isoDateTime));
}

/** "2026-11-24" → "24 พ.ย." */
export function formatShortDate(isoDate: string): string {
  return shortDateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}
