"use client";

import { useRef, useState } from "react";

import { ApiError, type CsvRowError, api } from "@/lib/api";
import { tradeErrorText } from "@/lib/trade-errors";

/** "นำเข้าจากไฟล์ CSV": all-or-nothing; shows every bad row when the file is rejected. */
export function CsvImport({ onImported }: { onImported: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string; rows: CsvRowError[] } | null>(null);
  const [showFormat, setShowFormat] = useState(false);

  async function onFile(file: File) {
    setPending(true);
    setResult(null);
    try {
      const { imported } = await api.importTrades(await file.text());
      setResult({ ok: true, text: `นำเข้า ${imported} รายการแล้ว`, rows: [] });
      onImported();
    } catch (err) {
      const e = err instanceof ApiError ? err : null;
      setResult({ ok: false, text: tradeErrorText(e, "import"), rows: e?.csvErrors ?? [] });
    } finally {
      setPending(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="space-y-2">
      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        id="csv-file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onFile(file);
        }}
      />
      <label
        htmlFor="csv-file"
        className={`flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-line-strong py-2.5 font-medium hover:bg-surface-2 ${
          pending ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <DownloadIcon />
        {pending ? "กำลังนำเข้า…" : "นำเข้าจากไฟล์ CSV"}
      </label>
      <button type="button" onClick={() => setShowFormat((v) => !v)} className="text-xs text-muted underline">
        รูปแบบไฟล์
      </button>
      {showFormat && (
        <div className="rounded-xl bg-surface-2 p-3 text-xs text-ink-2">
          <code className="num block whitespace-pre-wrap break-all">
            date,side,ticker,shares,price_usd,fee_usd,usd_thb{"\n"}2026-08-04,buy,VOO,1.5,585.40,0,33.20
          </code>
          <p className="mt-2 text-muted">
            ต้องมี ticker, shares, price_usd · date ว่าง = วันนี้ · side = buy/sell (หรือ ซื้อ/ขาย) · usd_thb ว่าง = เรท ธปท.
            ของวันนั้น · ถ้ามีแถวผิดจะไม่นำเข้าเลยสักแถว
          </p>
        </div>
      )}
      {result && (
        <div role={result.ok ? "status" : "alert"} className={`text-sm ${result.ok ? "text-up" : "text-down"}`}>
          <p>{result.text}</p>
          {result.rows.length > 0 && (
            <ul className="num mt-1 max-h-40 overflow-y-auto text-xs">
              {result.rows.map((r, i) => (
                <li key={i}>
                  บรรทัด {r.line}
                  {r.column ? ` (${r.column})` : ""}: {r.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
