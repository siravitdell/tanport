import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { earningsTimeText, epsText, fiscalLabel } from "./earnings.ts";

describe("earningsTimeText", () => {
  it("before the open: same evening in Bangkok", () => {
    // 2027-01-26 09:30 EST = 14:30 UTC = 21:30 Bangkok
    assert.equal(earningsTimeText("bmo", "2027-01-26T14:30:00Z", "2027-01-26"), "ก่อนตลาดเปิด (21:30 น. เวลาไทย)");
  });

  it("after the close: early next morning in Bangkok", () => {
    // 16:00 EDT = 20:00 UTC = 03:00 Bangkok next day
    assert.equal(
      earningsTimeText("amc", "2026-07-28T20:00:00Z", "2026-07-28"),
      "หลังตลาดปิด (03:00 น. เช้าวันถัดไป เวลาไทย)",
    );
  });

  it("no time known", () => {
    assert.equal(earningsTimeText("unknown", null, "2027-01-26"), "ยังไม่ระบุเวลา");
    assert.equal(earningsTimeText("dmh", null, "2027-01-26"), "ระหว่างตลาดเปิด");
    assert.equal(earningsTimeText("amc", null, "2026-12-25"), "หลังตลาดปิด");
  });
});

describe("eps and fiscal labels", () => {
  it("reported vs estimate, compared at the cent", () => {
    assert.equal(epsText("2.5252", "2.68"), "EPS จริง $2.68 · คาด $2.53 (ดีกว่าคาด)");
    assert.equal(epsText("1.30", "1.2"), "EPS จริง $1.20 · คาด $1.30 (ต่ำกว่าคาด)");
    assert.equal(epsText("0.701", "0.70"), "EPS จริง $0.70 · คาด $0.70 (ตามคาด)");
    assert.equal(epsText("-0.10", "-0.05"), "EPS จริง −$0.05 · คาด −$0.10 (ดีกว่าคาด)"); // a smaller loss
    assert.equal(epsText("4.9626", null), "คาด EPS $4.96");
    assert.equal(epsText(null, null), "");
  });

  it("fiscal label", () => {
    assert.equal(fiscalLabel(2, 2027), "Q2 FY2027");
    assert.equal(fiscalLabel(null, undefined), "");
  });
});
