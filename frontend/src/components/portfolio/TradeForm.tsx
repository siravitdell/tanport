"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, type FxResponse, type Position, type Side, api } from "@/lib/api";
import { formatShortDate } from "@/lib/dates";
import {
  addDecimals,
  formatDecimal,
  formatThb,
  formatUsd,
  isDecimal,
  mulDecimals,
  negate,
} from "@/lib/format";
import { tradeErrorText } from "@/lib/trade-errors";

interface Props {
  today: string;
  positions: Position[];
  onSaved: () => void;
}

const input =
  "num mt-1.5 w-full rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-ink outline-none placeholder:text-muted focus:border-ink";
const labelCls = "block text-sm font-medium text-ink-2";

export function TradeForm({ today, positions, onSaved }: Props) {
  const [side, setSide] = useState<Side>("buy");
  const [ticker, setTicker] = useState("");
  const [date, setDate] = useState(today);
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("0");
  const [rate, setRate] = useState("");
  const [rateEdited, setRateEdited] = useState(false);
  const [fx, setFx] = useState<FxResponse | null | undefined>(undefined); // null: none known
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const tickerRef = useRef<HTMLInputElement>(null);

  // The Bank of Thailand rate of the chosen date pre-fills the rate (until the user types one).
  useEffect(() => {
    if (!date) return;
    let active = true;
    api.fx(date).then(
      (r) => {
        if (!active) return;
        setFx(r);
        if (!rateEdited) setRate(r.usd_thb);
      },
      () => {
        if (active) setFx(null);
      },
    );
    return () => {
      active = false;
    };
  }, [date, rateEdited]);

  const symbol = ticker.trim().toUpperCase();
  const held = positions.find((p) => p.ticker === symbol);
  const valid = [shares, price, fee || "0", rate].every(isDecimal);
  const gross = valid ? mulDecimals(shares, price) : null;
  const totalUsd = gross ? addDecimals([gross, side === "buy" ? fee || "0" : negate(fee || "0")]) : null;
  const totalThb = totalUsd ? mulDecimals(totalUsd, rate) : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      const trade = await api.createTrade({
        side,
        ticker: symbol,
        trade_date: date,
        shares: shares.trim(),
        price_usd: price.trim(),
        fee_usd: (fee || "0").trim(),
        usd_thb: rate.trim() || null,
      });
      setMessage({
        ok: true,
        text: `บันทึกการ${side === "buy" ? "ซื้อ" : "ขาย"} ${trade.ticker} ${trade.shares} หุ้นแล้ว`,
      });
      setShares("");
      setPrice("");
      setFee("0");
      onSaved();
      tickerRef.current?.focus();
    } catch (err) {
      setMessage({ ok: false, text: tradeErrorText(err instanceof ApiError ? err : null) });
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-labelledby="trade-form">
      <h2 id="trade-form" className="text-lg font-bold">
        บันทึกรายการ
      </h2>

      <div role="tablist" className="grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
        {(["buy", "sell"] as const).map((s) => (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={side === s}
            onClick={() => {
              setSide(s);
              setMessage(null);
            }}
            className={`rounded-lg py-2.5 font-semibold ${
              side === s ? (s === "buy" ? "bg-pay-bg text-pay-ink" : "bg-surface text-down shadow-sm") : "text-muted"
            }`}
          >
            {s === "buy" ? "ซื้อ" : "ขาย"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className={labelCls}>
          หุ้น / ETF
          <input
            ref={tickerRef}
            required
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            list="held-tickers"
            autoCapitalize="characters"
            autoComplete="off"
            placeholder="VOO"
            className={`${input} uppercase`}
          />
          <datalist id="held-tickers">
            {positions.map((p) => (
              <option key={p.ticker} value={p.ticker} />
            ))}
          </datalist>
        </label>
        <label className={labelCls}>
          วันที่
          <input
            type="date"
            required
            max={today}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={input}
          />
        </label>
        <label className={labelCls}>
          จำนวนหุ้น
          <input
            required
            inputMode="decimal"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            placeholder="เช่น 0.8125"
            className={input}
          />
        </label>
        <label className={labelCls}>
          ราคาต่อหุ้น (USD)
          <input
            required
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="เช่น 598.20"
            className={input}
          />
        </label>
        <label className={labelCls}>
          ค่าธรรมเนียม (USD)
          <input inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} className={input} />
        </label>
        <label className={labelCls}>
          อัตราแลกเปลี่ยน (฿/$)
          <input
            required
            inputMode="decimal"
            value={rate}
            onChange={(e) => {
              setRate(e.target.value);
              setRateEdited(true);
            }}
            className={input}
          />
        </label>
      </div>

      <p className="text-xs leading-relaxed text-muted">
        {side === "sell" && symbol && (
          <span className="mb-1 block text-ink-2">
            {held ? `ถืออยู่ ${held.shares} หุ้น` : `ยังไม่มี ${symbol} ในพอร์ต`}
          </span>
        )}
        อัตราแลกเปลี่ยนเติมให้อัตโนมัติจาก ธปท. ตามวันที่ แก้เป็นเรทจริงที่โบรกให้ได้
        {fx && fx.is_fallback && ` (ไม่มีเรทวันนั้น ใช้ของ ${formatShortDate(fx.rate_date)})`}
        {fx === null && " (ยังไม่มีเรทของวันนั้น ใส่เอง)"}
        {rateEdited && fx && rate !== fx.usd_thb && (
          <>
            {" · "}
            <button
              type="button"
              className="underline"
              onClick={() => {
                setRate(fx.usd_thb);
                setRateEdited(false);
              }}
            >
              ใช้เรท ธปท. {formatDecimal(fx.usd_thb, 2)}
            </button>
          </>
        )}
      </p>

      <dl className="space-y-1.5 rounded-xl bg-surface-2 px-4 py-3 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-muted">{side === "buy" ? "ยอดซื้อรวมค่าธรรมเนียม" : "ยอดขายหักค่าธรรมเนียม"}</dt>
          <dd className="num font-semibold">{totalUsd ? formatUsd(totalUsd) : "–"}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted">เป็นเงินบาท</dt>
          <dd className="num font-semibold">{totalThb ? formatThb(totalThb) : "–"}</dd>
        </div>
      </dl>

      {message && (
        <p role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-up" : "text-down"}`}>
          {message.text}
        </p>
      )}

      <button
        type="submit"
        disabled={pending || !valid || !symbol}
        className="w-full rounded-xl bg-hero py-3 font-semibold text-hero-ink disabled:opacity-50"
      >
        {pending ? "กำลังบันทึก…" : side === "buy" ? "บันทึกการซื้อ" : "บันทึกการขาย"}
      </button>
    </form>
  );
}
