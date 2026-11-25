"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useUser } from "@/components/AuthProvider";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import type { QuotesResponse } from "@/lib/api";
import { formatShortDate, formatTime } from "@/lib/dates";
import { formatDecimal } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const NAV: Array<{ href: string; label: string; disabled?: boolean }> = [
  { href: "/", label: "ปฏิทิน" },
  { href: "/income", label: "รายได้ปันผล" },
  { href: "/portfolio", label: "พอร์ต" },
  { href: "/digest", label: "LINE digest", disabled: true }, // Phase 3
];

export function Header() {
  const pathname = usePathname();
  const user = useUser();
  const { data: quotes } = useApi<QuotesResponse>("/api/quotes");
  const onSettings = pathname.startsWith("/settings");

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-8 md:h-[72px] md:flex-nowrap md:py-0">
        <Link href="/" className="mr-auto flex items-center gap-3 text-xl font-bold md:mr-0">
          <Logo />
          TanPort
        </Link>

        {/* phones: its own row under the logo */}
        <nav
          className="order-last flex w-full items-center gap-1 whitespace-nowrap md:order-none md:mx-auto md:w-auto"
          aria-label="หลัก"
        >
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            if (item.disabled) {
              return (
                <span
                  key={item.href}
                  title="เร็ว ๆ นี้"
                  aria-disabled
                  className="hidden cursor-not-allowed rounded-xl px-4 py-2 font-medium text-muted sm:block"
                >
                  {item.label}
                </span>
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "rounded-xl bg-hero px-4 py-2 font-semibold text-hero-ink"
                    : "rounded-xl px-4 py-2 font-medium text-ink-2 hover:bg-surface-2"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-3">
          <FxNote quotes={quotes} />
          <Link
            href="/settings"
            aria-label="ตั้งค่า"
            aria-current={onSettings ? "page" : undefined}
            title={user ? `ตั้งค่า · ${user.email}` : "ตั้งค่า"}
            className={`grid size-10 place-items-center rounded-xl border ${
              onSettings ? "border-ink bg-surface-2 text-ink" : "border-line-strong bg-surface text-ink hover:bg-surface-2"
            }`}
          >
            <GearIcon />
          </Link>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

/** "ราคา ณ 04:00 · 1 USD = 32.94 บาท" — which time the prices are from and which FX rate is used. */
function FxNote({ quotes }: { quotes: QuotesResponse | undefined }) {
  if (!quotes) return null;
  const parts: string[] = [];
  if (quotes.as_of_utc) parts.push(`ราคา ณ ${formatTime(quotes.as_of_utc)}`);
  if (quotes.fx) {
    const rate = `1 USD = ${formatDecimal(quotes.fx.usd_thb, 2)} บาท`;
    parts.push(quotes.fx.is_fallback ? `${rate} (เรท ${formatShortDate(quotes.fx.rate_date)})` : rate);
  }
  if (!parts.length) return null;
  return <p className="num hidden text-sm text-muted lg:block">{parts.join(" · ")}</p>;
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path
        d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"
        strokeLinejoin="round"
      />
    </svg>
  );
}