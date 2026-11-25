/** Thai messages for the trade API's errors (pure; tested). */

export interface ErrorLike {
  status: number;
  message: string;
}

const OVERSELL = /cannot sell (\S+) (\S+) on (\S+): only (\S+) held/;

export function tradeErrorText(err: ErrorLike | null, action: "save" | "delete" | "import" = "save"): string {
  if (!err) return "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ลองใหม่อีกครั้ง";
  const m = OVERSELL.exec(err.message);
  if (err.status === 409 && action === "delete") {
    return "ลบไม่ได้: รายการขายที่ตามมาจะขายเกินจำนวนหุ้นที่ถืออยู่ ลบรายการขายนั้นก่อน";
  }
  if (err.status === 409 && m) {
    const [, shares, ticker, day, held] = m;
    return `ขาย ${ticker} ${shares} หุ้นไม่ได้: วันที่ ${day} ถืออยู่ ${held} หุ้น`;
  }
  if (err.status === 422 && /enter the rate/.test(err.message)) {
    return "ยังไม่มีเรท ธปท. ของวันนั้น ใส่อัตราแลกเปลี่ยนเอง";
  }
  if (err.status === 422 && /future/.test(err.message)) return "วันที่อยู่ในอนาคต";
  if (err.status === 404) return "ไม่พบรายการนี้แล้ว";
  if (err.status === 415) return "ไฟล์ต้องเป็น CSV";
  if (err.status === 413) return "ไฟล์ใหญ่เกินไป";
  if (err.status === 422) return action === "import" ? "ไฟล์มีข้อมูลที่ไม่ถูกต้อง" : `ข้อมูลไม่ถูกต้อง: ${err.message}`;
  return `เกิดข้อผิดพลาด (${err.status})`;
}
