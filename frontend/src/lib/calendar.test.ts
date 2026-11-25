import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  type EventLike,
  type Filter,
  addMonths,
  bangkokToday,
  cellChips,
  chipFor,
  daysInMonth,
  isWeekend,
  monthGrid,
  monthRange,
  sparkPoints,
  visibleEvents,
} from "./calendar.ts";

const M = "−";

describe("months", () => {
  it("days in month, leap years", () => {
    assert.equal(daysInMonth({ year: 2026, month: 12 }), 31);
    assert.equal(daysInMonth({ year: 2026, month: 2 }), 28);
    assert.equal(daysInMonth({ year: 2028, month: 2 }), 29);
  });

  it("addMonths across years", () => {
    assert.deepEqual(addMonths({ year: 2026, month: 12 }, 1), { year: 2027, month: 1 });
    assert.deepEqual(addMonths({ year: 2026, month: 1 }, -1), { year: 2025, month: 12 });
    assert.deepEqual(addMonths({ year: 2026, month: 5 }, -17), { year: 2024, month: 12 });
  });

  it("monthRange", () => {
    assert.deepEqual(monthRange({ year: 2026, month: 2 }), { from: "2026-02-01", to: "2026-02-28" });
  });

  it("December 2026 grid matches the mockup: Mon 30 Nov … Sun 3 Jan", () => {
    const weeks = monthGrid({ year: 2026, month: 12 });
    assert.equal(weeks.length, 5);
    assert.ok(weeks.every((w) => w.length === 7));
    assert.deepEqual(weeks[0]?.[0], { iso: "2026-11-30", day: 30, inMonth: false });
    assert.deepEqual(weeks[0]?.[1], { iso: "2026-12-01", day: 1, inMonth: true });
    assert.deepEqual(weeks[4]?.[6], { iso: "2027-01-03", day: 3, inMonth: false });
  });

  it("a month starting on Monday has no leading days", () => {
    const weeks = monthGrid({ year: 2026, month: 6 }); // 1 June 2026 is a Monday
    assert.equal(weeks[0]?.[0]?.iso, "2026-06-01");
  });

  it("Bangkok date, not UTC", () => {
    // 2026-12-15 18:00 UTC = 2026-12-16 01:00 in Bangkok
    assert.equal(bangkokToday(new Date("2026-12-15T18:00:00Z")), "2026-12-16");
  });

  it("weekends", () => {
    assert.equal(isWeekend("2026-12-19"), true); // Saturday
    assert.equal(isWeekend("2026-12-20"), true);
    assert.equal(isWeekend("2026-12-21"), false);
  });
});

const ev = (type: string, ticker: string | null, payload: Record<string, unknown> = {}, is_estimate = false): EventLike => ({
  type,
  ticker,
  payload,
  is_estimate,
});

describe("chips", () => {
  it("labels follow the mockup and never use color alone", () => {
    assert.deepEqual(chipFor(ev("price_move", "AMZN", { change_pct: "3.104" })), {
      kind: "up",
      label: "▲ AMZN +3.1%",
      estimate: false,
    });
    assert.deepEqual(chipFor(ev("price_move", "NVDA", { change_pct: "-5.4" })), {
      kind: "down",
      label: `▼ NVDA ${M}5.4%`,
      estimate: false,
    });
    assert.equal(chipFor(ev("dividend_pay", "V")).label, "เงินเข้า · V");
    assert.equal(chipFor(ev("ex_dividend", "SCHD")).label, "XD · SCHD");
    assert.equal(chipFor(ev("macro", null, { name: "FOMC" })).label, "Macro · FOMC");
    assert.equal(chipFor(ev("dividend_pay", "VOO", {}, true)).estimate, true);
  });

  it("filters and orders", () => {
    const events = [
      ev("ex_dividend", "VOO"),
      ev("dividend_pay", "V"),
      ev("price_move", "AMZN", { change_pct: "3.1" }),
      ev("macro", null, { name: "CPI" }),
    ];
    const all = new Set<Filter>(["price", "dividend", "earnings", "news", "macro"]);
    assert.deepEqual(
      visibleEvents(events, all).map((e) => e.type),
      ["price_move", "macro", "dividend_pay", "ex_dividend"],
    );
    assert.deepEqual(
      visibleEvents(events, new Set<Filter>(["dividend"])).map((e) => e.ticker),
      ["V", "VOO"],
    );
  });

  it("at most 3 chips, then +N", () => {
    const events = ["A", "B", "C", "D", "E"].map((t) => ev("news", t));
    const { chips, more } = cellChips(events);
    assert.equal(chips.length, 3);
    assert.equal(more, 2);
    assert.equal(cellChips(events.slice(0, 2)).more, 0);
  });
});

describe("sparkPoints", () => {
  it("scales min..max into the box, oldest on the left", () => {
    assert.equal(sparkPoints(["10", "20", "15"], 104, 34), "2.0,32.0 52.0,2.0 102.0,17.0");
  });

  it("flat series sits in the middle; one point draws nothing", () => {
    assert.equal(sparkPoints(["5", "5"], 10, 20), "2.0,10.0 8.0,10.0");
    assert.equal(sparkPoints(["5"], 10, 20), "");
  });
});
