import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { type MonthLike, concentration, monthBars, ratioPct } from "./income.ts";

// The mockup's year: 480/42/505/42/520/42 received, 534 upcoming in December.
const MOCKUP: Record<number, [string, string]> = {
  3: ["480", "0"],
  4: ["42", "0"],
  6: ["505", "0"],
  7: ["42", "0"],
  9: ["520", "0"],
  10: ["42", "0"],
  12: ["0", "534"],
};

function year(data: Record<number, [string, string]>): MonthLike[] {
  return Array.from({ length: 12 }, (_, i) => {
    const [received_thb, upcoming_thb] = data[i + 1] ?? ["0", "0"];
    return { month: i + 1, received_thb, upcoming_thb };
  });
}

describe("ratioPct", () => {
  const cases: Array<[string, string, string | null]> = [
    ["94", "100", "94"],
    ["2039", "2165", "94"], // 94.18
    ["1", "8", "13"], // 12.5 → half-up
    ["0", "10", "0"],
    ["5", "0", null],
    ["0.000001", "0.000002", "50"],
  ];
  for (const [part, whole, expected] of cases) {
    it(`${part}/${whole} → ${expected}`, () => assert.equal(ratioPct(part, whole), expected));
  }
});

describe("monthBars", () => {
  it("totals and drawing ratios against the tallest month", () => {
    const bars = monthBars(year(MOCKUP));
    assert.equal(bars.length, 12);
    assert.equal(bars[11]?.total, "534");
    assert.equal(bars[11]?.upcomingRatio, 1);
    assert.equal(bars[11]?.receivedRatio, 0);
    assert.equal(bars[0]?.total, "0");
    assert.ok(Math.abs((bars[2]?.receivedRatio ?? 0) - 480 / 534) < 1e-9);
  });

  it("an empty year draws nothing", () => {
    assert.ok(monthBars(year({})).every((b) => b.receivedRatio === 0 && b.upcomingRatio === 0));
  });

  it("a month can be part received, part upcoming", () => {
    const [bar] = monthBars([{ month: 11, received_thb: "100.5", upcoming_thb: "99.5" }]);
    assert.equal(bar?.total, "200.0");
    assert.equal(bar?.receivedRatio, 100.5 / 200);
  });
});

describe("concentration", () => {
  it("matches the mockup note: 4 months = 94 %, five months without income", () => {
    assert.deepEqual(concentration(year(MOCKUP)), {
      topMonths: [3, 6, 9, 12],
      sharePct: "94",
      emptyMonths: [1, 2, 5, 8, 11],
    });
  });

  it("nothing to say with no income or a single paying month", () => {
    assert.equal(concentration(year({})), null);
    assert.equal(concentration(year({ 6: ["100", "0"] })), null);
  });

  it("fewer paying months than `top`", () => {
    assert.deepEqual(concentration(year({ 2: ["10", "0"], 8: ["30", "0"] })), {
      topMonths: [2, 8],
      sharePct: "100",
      emptyMonths: [1, 3, 4, 5, 6, 7, 9, 10, 11, 12],
    });
  });
});
