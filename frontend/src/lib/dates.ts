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

/** "2026-11-25T21:00:00Z" → "04:00" in Bangkok. */
export function formatTime(isoDateTime: string): string {
  return timeFmt.format(new Date(isoDateTime));
}

/** "2026-11-24" → "24 พ.ย." */
export function formatShortDate(isoDate: string): string {
  return shortDateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}
