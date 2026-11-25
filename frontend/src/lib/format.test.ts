import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  arrow,
  direction,
  formatDecimal,
  formatPct,
  formatSigned,
  formatThb,
  formatThbSigned,
  formatUsd,
} from "./format.ts";

const M = "−";

describe("formatDecimal", () => {
  const cases: Array<[string, number, string]> = [
    ["179268.4", 0, "179,268"],
    ["179268.5", 0, "179,269"],
    ["1.005", 2, "1.01"], // half-up on the digits; a float would give 1.00
    ["2.675", 2, "2.68"],
    ["-1.005", 2, `${M}1.01`], // half away from zero
    ["-0.004", 2, "0.00"], // rounds to zero: no minus
    ["0", 2, "0.00"],
    ["12.5", 4, "12.5000"],
    ["999.995", 2, "1,000.00"],
    ["1234567.891", 2, "1,234,567.89"],
    ["0.000001", 6, "0.000001"],
    ["+3", 1, "3.0"],
    ["99.5", 0, "100"],
  ];
  for (const [input, dp, expected] of cases) {
    it(`${input} @${dp} → ${expected}`, () => {
      assert.equal(formatDecimal(input, dp), expected);
    });
  }

  it("rejects non-decimal input", () => {
    for (const bad of ["", "abc", "1e5", "1.2.3", "NaN", " - 1"]) {
      assert.throws(() => formatDecimal(bad, 2), /not a decimal string/);
    }
  });
});

describe("signed formats", () => {
  const cases: Array<[string, string, string]> = [
    ["0.4012", "+0.40%", "up"],
    ["-1.38", `${M}1.38%`, "down"],
    ["0", "0.00%", "flat"],
    ["-0.001", "0.00%", "flat"],
    ["0.005", "+0.01%", "up"],
  ];
  for (const [input, pct, dir] of cases) {
    it(`${input} → ${pct} (${dir})`, () => {
      assert.equal(formatPct(input), pct);
      assert.equal(direction(input), dir);
    });
  }

  it("formatSigned", () => {
    assert.equal(formatSigned("2.444", 2), "+2.44");
    assert.equal(formatSigned("-5.4", 2), `${M}5.40`);
  });
});

describe("currency", () => {
  it("THB", () => {
    assert.equal(formatThb("179268.42"), "฿179,268");
    assert.equal(formatThb("534.5"), "฿535");
    assert.equal(formatThbSigned("714.2"), "+฿714");
    assert.equal(formatThbSigned("-2484.4"), `${M}฿2,484`);
    assert.equal(formatThbSigned("0.2"), "฿0");
  });

  it("USD", () => {
    assert.equal(formatUsd("611.7234"), "$611.72");
    assert.equal(formatUsd("28.725"), "$28.73");
  });
});

describe("arrow", () => {
  it("never relies on color alone", () => {
    assert.equal(arrow("up"), "▲");
    assert.equal(arrow("down"), "▼");
    assert.equal(arrow("flat"), "");
  });
});
