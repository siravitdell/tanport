"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useUser } from "@/components/AuthProvider";
import { ApiError, type SettingsResponse, api } from "@/lib/api";
import { addDecimals, formatDecimal, isDecimal, shiftDecimal } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export function SettingsView() {
  const { data, error, reload } = useApi<SettingsResponse>("/api/settings");
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold sm:text-4xl">ตั้งค่า</h1>
        <p className="mt-2 text-muted">ใช้กับบัญชีของคุณเท่านั้น</p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-down">
          โหลดข้อมูลไม่สำเร็จ: {error.message}
        </p>
      )}
      {/* mounted once with the loaded values; after a save its own state already matches */}
      {data ? <SettingsForm initial={data} onSaved={reload} /> : !error && <p className="text-sm text-muted">กำลังโหลด…</p>}
      <Account />
    </div>
  );
}

interface Row {
  id: number;
  ticker: string;
  pct: string;
}

const RATES = [
  { value: "0.15", label: "15%", note: "ยื่น W-8BEN แล้ว (สนธิสัญญาภาษีไทย–สหรัฐฯ)" },
  { value: "0.3", label: "30%", note: "ยังไม่ได้ยื่น W-8BEN" },
];

const card = "rounded-2xl border border-line bg-surface p-5 sm:p-6";
const input =
  "num rounded-xl border border-line-strong bg-surface px-3 py-2 text-ink outline-none focus:border-ink";

function SettingsForm({ initial, onSaved }: { initial: SettingsResponse; onSaved: () => void }) {
  const [rate, setRate] = useState(initial.withholding_rate);
  const [threshold, setThreshold] = useState(initial.big_move_threshold_pct);
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(initial.dca_split).map(([ticker, pct], id) => ({ id, ticker, pct })),
  );
  const [nextId, setNextId] = useState(rows.length);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const pctValid = rows.every((r) => isDecimal(r.pct));
  const total = pctValid ? addDecimals(rows.map((r) => r.pct)) : null;
  const totalOk = total !== null && formatDecimal(total, 6) === "100.000000";
  const tickersOk = rows.length > 0 && rows.every((r) => /^[A-Za-z][A-Za-z0-9.\-]{0,15}$/.test(r.ticker.trim()));
  const thresholdOk = isDecimal(threshold) && Number(threshold) > 0 && Number(threshold) <= 100;
  const known = RATES.some((r) => r.value === normalizeRate(rate));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      await api.updateSettings({
        withholding_rate: rate,
        big_move_threshold_pct: threshold.trim(),
        dca_split: Object.fromEntries(rows.map((r) => [r.ticker.trim().toUpperCase(), r.pct.trim()])),
      });
      setMessage({ ok: true, text: "บันทึกแล้ว" });
      onSaved();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof ApiError ? `บันทึกไม่ได้: ${err.message}` : "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้" });
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-6">
      <fieldset className={card}>
        <legend className="sr-only">ภาษีปันผล</legend>
        <h2 className="text-lg font-bold">ภาษีหัก ณ ที่จ่ายของสหรัฐฯ</h2>
        <p className="mt-1 text-sm text-muted">ใช้คำนวณปันผลสุทธิในปฏิทินและหน้ารายได้</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {RATES.map((r) => (
            <label
              key={r.value}
              className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${
                normalizeRate(rate) === r.value ? "border-ink" : "border-line-strong"
              }`}
            >
              <input
                type="radio"
                name="withholding"
                value={r.value}
                checked={normalizeRate(rate) === r.value}
                onChange={() => setRate(r.value)}
                className="mt-1 accent-current"
              />
              <span>
                <span className="num block text-lg font-semibold">{r.label}</span>
                <span className="text-sm text-muted">{r.note}</span>
              </span>
            </label>
          ))}
        </div>
        {!known && (
          <p className="mt-2 text-sm text-muted">ตอนนี้ตั้งไว้ {formatDecimal(shiftDecimal(rate, 2), 2)}%</p>
        )}
      </fieldset>

      <section className={card}>
        <h2 className="text-lg font-bold">ราคาขยับแรง</h2>
        <label className="mt-3 flex flex-wrap items-center gap-3 text-sm text-ink-2">
          หุ้นที่ขยับเกิน ±
          <input
            inputMode="decimal"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            aria-invalid={!thresholdOk}
            className={`${input} w-20 text-center`}
          />
          % ในวันเดียว จะขึ้นเป็นรายการบนปฏิทิน
        </label>
        {!thresholdOk && <p className="mt-2 text-sm text-down">ใส่ตัวเลขมากกว่า 0 และไม่เกิน 100</p>}
      </section>

      <section className={card}>
        <h2 className="text-lg font-bold">สัดส่วน DCA</h2>
        <p className="mt-1 text-sm text-muted">เงินที่ DCA แต่ละเดือนแบ่งไปหุ้นไหนกี่ % ใช้ในหน้าคาดการณ์ปันผล (เร็ว ๆ นี้)</p>
        <ul className="mt-4 space-y-2">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-2">
              <input
                aria-label="หุ้น"
                value={r.ticker}
                onChange={(e) => setRows((rs) => rs.map((x) => (x.id === r.id ? { ...x, ticker: e.target.value } : x)))}
                className={`${input} w-32 uppercase`}
              />
              <input
                aria-label={`สัดส่วนของ ${r.ticker}`}
                inputMode="decimal"
                value={r.pct}
                onChange={(e) => setRows((rs) => rs.map((x) => (x.id === r.id ? { ...x, pct: e.target.value } : x)))}
                className={`${input} w-24 text-right`}
              />
              <span className="text-muted">%</span>
              <button
                type="button"
                onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}
                aria-label={`ลบ ${r.ticker}`}
                className="ml-auto rounded-lg px-2 py-1 text-sm text-muted hover:bg-surface-2 hover:text-down"
              >
                ลบ
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              setRows((rs) => [...rs, { id: nextId, ticker: "", pct: "0" }]);
              setNextId((n) => n + 1);
            }}
            className="rounded-xl border border-line-strong px-3 py-1.5 text-sm hover:bg-surface-2"
          >
            + เพิ่มหุ้น
          </button>
          <p className={`num text-sm ${totalOk ? "text-muted" : "text-down"}`}>
            รวม {total !== null ? formatDecimal(total, 2) : "–"}%{!totalOk && " (ต้องเท่ากับ 100%)"}
          </p>
        </div>
      </section>

      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={pending || !totalOk || !tickersOk || !thresholdOk}
          className="rounded-xl bg-hero px-6 py-2.5 font-semibold text-hero-ink disabled:opacity-50"
        >
          {pending ? "กำลังบันทึก…" : "บันทึก"}
        </button>
        {message && (
          <p role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-up" : "text-down"}`}>
            {message.text}
          </p>
        )}
      </div>
    </form>
  );
}

/** "0.150000" → "0.15", so the API's value matches a radio option. */
function normalizeRate(value: string): string {
  return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}

function Account() {
  const user = useUser();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <section className={card}>
      <h2 className="text-lg font-bold">บัญชี</h2>
      <p className="mt-2 text-sm text-ink-2">
        {user ? (
          <>
            {user.display_name && <span className="font-semibold">{user.display_name} · </span>}
            {user.email}
          </>
        ) : (
          "…"
        )}
      </p>
      <button
        type="button"
        disabled={pending}
        onClick={async () => {
          setPending(true);
          try {
            await api.logout();
          } finally {
            router.replace("/login");
          }
        }}
        className="mt-4 rounded-xl border border-line-strong px-4 py-2 text-sm hover:bg-surface-2 disabled:opacity-60"
      >
        ออกจากระบบ
      </button>
    </section>
  );
}
