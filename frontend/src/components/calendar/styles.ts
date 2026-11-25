import type { ChipKind, Filter } from "@/lib/calendar";
import type { Direction } from "@/lib/format";

/** Token classes per chip kind. Price moves are outlined, everything else is a tinted pill. */
export const CHIP_CLASS: Record<ChipKind, string> = {
  up: "border border-line-strong bg-surface text-up",
  down: "border border-line-strong bg-surface text-down",
  pay: "bg-pay-bg text-pay-ink",
  xd: "bg-xd-bg text-xd-ink",
  earn: "bg-earn-bg text-earn-ink",
  news: "bg-news-bg text-news-ink",
  macro: "bg-macro-bg text-macro-ink",
};

/** Event dots on phone-width day cells. */
export const CHIP_DOT: Record<ChipKind, string> = {
  up: "bg-up",
  down: "bg-down",
  pay: "bg-pay-ink",
  xd: "bg-xd-ink",
  earn: "bg-earn-ink",
  news: "bg-news-ink",
  macro: "bg-macro-ink",
};

/** Not-yet-declared dividends: dashed outline (plus "ประมาณการ" in titles), never color alone. */
export const ESTIMATE_CLASS = "outline outline-1 outline-dashed outline-current -outline-offset-1";

export const FILTER_META: Record<Filter, { label: string; dot: string }> = {
  price: { label: "ราคา", dot: "bg-up" },
  dividend: { label: "ปันผล", dot: "bg-pay-ink" },
  earnings: { label: "งบ", dot: "bg-earn-ink" },
  news: { label: "ข่าว", dot: "bg-news-ink" },
  macro: { label: "Macro", dot: "bg-macro-ink" },
};

export const DIR_TEXT: Record<Direction, string> = {
  up: "text-up",
  down: "text-down",
  flat: "text-muted",
};
