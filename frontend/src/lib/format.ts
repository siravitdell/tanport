/**
 * Display formatting for the decimal strings the API returns ("12.5", "-0.4012").
 * Money is never turned into a JS number: rounding is done on the digits with BigInt,
 * half-up (away from zero), like ROUND_HALF_UP in the backend.
 */

export type Direction = "up" | "down" | "flat";

const MINUS = "−"; // "−", the real minus sign
const DECIMAL_RE = /^([+-]?)(\d+)(?:\.(\d+))?$/;

interface Rounded {
  negative: boolean; // false when the rounded value is zero
  intPart: string;
  fracPart: string;
}

function roundHalfUp(value: string, dp: number): Rounded {
  const match = DECIMAL_RE.exec(value.trim());
  if (!match) throw new Error(`not a decimal string: ${JSON.stringify(value)}`);
  const [, sign, intDigits, frac = ""] = match;
  const padded = frac.padEnd(dp + 1, "0");
  let scaled = BigInt(intDigits + padded.slice(0, dp));
  if (Number(padded[dp]) >= 5) scaled += BigInt(1);

  const digits = scaled.toString().padStart(dp + 1, "0");
  const intPart = digits.slice(0, digits.length - dp);
  const fracPart = dp > 0 ? digits.slice(-dp) : "";
  return { negative: sign === "-" && scaled !== BigInt(0), intPart, fracPart };
}

function groupThousands(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function body(r: Rounded): string {
  const grouped = groupThousands(r.intPart);
  return r.fracPart ? `${grouped}.${r.fracPart}` : grouped;
}

/** "179268.4" → "179,268" (dp 0); "-1.005" → "−1.01" (dp 2). */
export function formatDecimal(value: string, dp: number): string {
  const r = roundHalfUp(value, dp);
  return (r.negative ? MINUS : "") + body(r);
}

/** Always shows the sign: "+0.40", "−1.38", "0.00" for zero. */
export function formatSigned(value: string, dp: number): string {
  const r = roundHalfUp(value, dp);
  if (r.negative) return MINUS + body(r);
  return (/[1-9]/.test(r.intPart + r.fracPart) ? "+" : "") + body(r);
}

function parts(value: string): { negative: boolean; digits: string; scale: number } {
  const match = DECIMAL_RE.exec(value.trim());
  if (!match) throw new Error(`not a decimal string: ${JSON.stringify(value)}`);
  const [, sign, intDigits = "", frac = ""] = match;
  return { negative: sign === "-", digits: intDigits + frac, scale: frac.length };
}

function fromScaled(n: bigint, scale: number): string {
  const negative = n < BigInt(0);
  const digits = (negative ? -n : n).toString().padStart(scale + 1, "0");
  const intPart = digits.slice(0, digits.length - scale);
  const frac = scale > 0 ? `.${digits.slice(-scale)}` : "";
  return `${negative ? "-" : ""}${intPart}${frac}`;
}

/** Exact sum of decimal strings: addDecimals(["0.1", "0.2"]) → "0.3". */
export function addDecimals(values: string[]): string {
  const ps = values.map(parts);
  const scale = Math.max(0, ...ps.map((p) => p.scale));
  let total = BigInt(0);
  for (const p of ps) {
    const n = BigInt(p.digits + "0".repeat(scale - p.scale));
    total += p.negative ? -n : n;
  }
  return fromScaled(total, scale);
}

/** True for a plain decimal string ("12", "-0.5", "1.25"): what the API and the forms accept. */
export function isDecimal(value: string): boolean {
  return DECIMAL_RE.test(value.trim());
}

/** Exact product: mulDecimals("1.5", "585.40") → "878.100". */
export function mulDecimals(a: string, b: string): string {
  const x = parts(a);
  const y = parts(b);
  const n = BigInt(x.digits) * BigInt(y.digits);
  return fromScaled(x.negative !== y.negative ? -n : n, x.scale + y.scale);
}

/** "-" in front of a decimal string, the sign of "-x" flipped. */
export function negate(value: string): string {
  const v = value.trim();
  return v.startsWith("-") ? v.slice(1) : v.startsWith("+") ? `-${v.slice(1)}` : `-${v}`;
}

/** Exact multiply by 10^places: shiftDecimal("0.15", 2) → "15.00" (a rate as a percent). */
export function shiftDecimal(value: string, places: number): string {
  const p = parts(value);
  let n = BigInt(p.digits);
  let scale = p.scale - places;
  if (scale < 0) {
    n *= BigInt(10) ** BigInt(-scale);
    scale = 0;
  }
  return fromScaled(p.negative ? -n : n, scale);
}

/** "0.4012" → "+0.40%". Input is already in percent (1.5 means +1.5 %). */
export function formatPct(value: string, dp = 2): string {
  return `${formatSigned(value, dp)}%`;
}

/** "179268.4" → "฿179,268". */
export function formatThb(value: string, dp = 0): string {
  const r = roundHalfUp(value, dp);
  return `${r.negative ? MINUS : ""}฿${body(r)}`;
}

/** "714.2" → "+฿714", "-2484" → "−฿2,484". */
export function formatThbSigned(value: string, dp = 0): string {
  const r = roundHalfUp(value, dp);
  if (r.negative) return `${MINUS}฿${body(r)}`;
  return `${/[1-9]/.test(r.intPart + r.fracPart) ? "+" : ""}฿${body(r)}`;
}

/** "611.7234" → "$611.72". */
export function formatUsd(value: string, dp = 2): string {
  const r = roundHalfUp(value, dp);
  return `${r.negative ? MINUS : ""}$${body(r)}`;
}

/** Direction after rounding to dp, so "+0.00%" is never shown as up or down. */
export function direction(value: string, dp = 2): Direction {
  const r = roundHalfUp(value, dp);
  if (r.negative) return "down";
  return /[1-9]/.test(r.intPart + r.fracPart) ? "up" : "flat";
}

/** ▲ / ▼ arrow so a move is never shown by color alone. */
export function arrow(dir: Direction): string {
  return dir === "up" ? "▲" : dir === "down" ? "▼" : "";
}
