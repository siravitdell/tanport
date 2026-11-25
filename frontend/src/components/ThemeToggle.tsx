"use client";

import { useEffect, useSyncExternalStore } from "react";

import { type Theme, applyTheme, readStoredTheme, storeTheme, systemTheme } from "@/lib/theme";

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

const currentTheme = (): Theme =>
  document.documentElement.dataset.theme === "dark" ? "dark" : "light";

export function ThemeToggle() {
  // null on the server: the theme is only known in the browser.
  const theme = useSyncExternalStore<Theme | null>(subscribe, currentTheme, () => null);

  // No stored choice = follow the OS, live.
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onOsChange = () => {
      if (readStoredTheme() === null) applyTheme(systemTheme());
    };
    media.addEventListener("change", onOsChange);
    return () => media.removeEventListener("change", onOsChange);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? "เปลี่ยนเป็นธีมมืด" : "เปลี่ยนเป็นธีมสว่าง";

  return (
    <button
      type="button"
      onClick={() => {
        applyTheme(next);
        storeTheme(next);
      }}
      aria-label={label}
      title={label}
      className="grid size-10 place-items-center rounded-xl border border-line-strong bg-surface text-ink transition-colors hover:bg-surface-2"
    >
      {theme === "dark" ? <SunIcon /> : theme === "light" ? <MoonIcon /> : null}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" strokeLinejoin="round" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path
        d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
