"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useUser } from "@/components/AuthProvider";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { type QuotesResponse, api } from "@/lib/api";
import { formatShortDate, formatTime } from "@/lib/dates";
import { formatDecimal } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const NAV: Array<{ href: string; label: string; disabled?: boolean }> = [
  { href: "/", label: "ปฏิทิน" },
  { href: "/income", label: "รายได้ปันผล" },
  { href: "/digest", label: "LINE digest", disabled: true }, // Phase 3
];

export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const { data: quotes } = useApi<QuotesResponse>("/api/quotes");
  const [loggingOut, setLoggingOut] = useState(false);

  async function logout() {
    setLoggingOut(true);
    try {
      await api.logout();
    } finally {
      router.replace("/login");
    }
  }

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
          <button
            type="button"
            onClick={logout}
            disabled={loggingOut}
            title={user?.email}
            className="whitespace-nowrap rounded-xl px-3 py-2 text-sm text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-60"
          >
            ออกจากระบบ
          </button>
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
