import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { tradeErrorText } from "./trade-errors.ts";

describe("tradeErrorText", () => {
  it("explains an oversell with the backend's numbers", () => {
    assert.equal(
      tradeErrorText({ status: 409, message: "cannot sell 3 KO on 2026-11-01: only 2 held then" }),
      "ขาย KO 3 หุ้นไม่ได้: วันที่ 2026-11-01 ถืออยู่ 2 หุ้น",
    );
  });

  it("a refused delete says what to do", () => {
    const text = tradeErrorText(
      { status: 409, message: "deleting this trade would leave a later sale uncovered: cannot sell 1 KO on 2026-11-01: only 0 held then" },
      "delete",
    );
    assert.match(text, /^ลบไม่ได้/);
  });

  it("missing FX rate, future date, generic", () => {
    assert.match(tradeErrorText({ status: 422, message: "no USD/THB rate known for 2026-01-01: enter the rate (usd_thb)" }), /ใส่อัตราแลกเปลี่ยนเอง/);
    assert.equal(tradeErrorText({ status: 422, message: "trade_date is in the future" }), "วันที่อยู่ในอนาคต");
    assert.equal(tradeErrorText({ status: 422, message: "x" }, "import"), "ไฟล์มีข้อมูลที่ไม่ถูกต้อง");
    assert.equal(tradeErrorText({ status: 500, message: "boom" }), "เกิดข้อผิดพลาด (500)");
    assert.match(tradeErrorText(null), /เชื่อมต่อเซิร์ฟเวอร์ไม่ได้/);
  });
});
