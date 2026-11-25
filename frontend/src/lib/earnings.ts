/** Thai wording for earnings announcements (pure; tested). */

import { formatDecimal, formatUsd } from "./format.ts";

const BKK_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Bangkok",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const BKK_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" });

/**
 * "ก่อนตลาดเปิด (21:30 น.)", "หลังตลาดปิด (04:00 น. เช้าวันถัดไป)", "ระหว่างตลาดเปิด", "ยังไม่ระบุเวลา".
 * `usDate` is the event's US date; times are shown in Bangkok.
 */
export function earningsTimeText(hour: string, timeUtc: string | null, usDate: string): string {
  const label =
    hour === "bmo" ? "ก่อนตลาดเปิด" : hour === "amc" ? "หลังตลาดปิด" : hour === "dmh" ? "ระหว่างตลาดเปิด" : null;
  if (!label) return "ยังไม่ระบุเวลา";
  if (!timeUtc) return label;
  const at = new Date(timeUtc);
  const nextDay = BKK_DATE.format(at) > usDate;
  return `${label} (${BKK_TIME.format(at)} น.${nextDay ? " เช้าวันถัดไป" : ""} เวลาไทย)`;
}

/** "Q2 FY2027" or "" */
export function fiscalLabel(quarter: unknown, fiscalYear: unknown): string {
  const q = typeof quarter === "number" ? `Q${quarter}` : "";
  const y = typeof fiscalYear === "number" ? `FY${fiscalYear}` : "";
  return [q, y].filter(Boolean).join(" ");
}

/** "EPS จริง $2.68 · คาด $2.53 (ดีกว่าคาด)" / "คาด EPS $4.96" / "" */
export function epsText(estimate: string | null, actual: string | null): string {
  const est = estimate ? formatUsd(estimate) : null;
  if (actual) {
    const act = formatUsd(actual);
    if (!est || !estimate) return `EPS จริง ${act}`;
    const verdict = compare(actual, estimate);
    return `EPS จริง ${act} · คาด ${est}${verdict ? ` (${verdict})` : ""}`;
  }
  return est ? `คาด EPS ${est}` : "";
}

/** Rounded to the cent, as shown: no "beat" on a difference nobody can see. */
function compare(actual: string, estimate: string): string {
  const a = formatDecimal(actual, 2);
  const e = formatDecimal(estimate, 2);
  if (a === e) return "ตามคาด";
  const toCents = (s: string) => BigInt(s.replace("−", "-").replace(/[,.]/g, ""));
  return toCents(a) > toCents(e) ? "ดีกว่าคาด" : "ต่ำกว่าคาด";
}
