export function Logo() {
  return (
    <span className="grid size-10 place-items-center rounded-xl bg-hero text-hero-ink" aria-hidden>
      <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 10h18M8 3v4M16 3v4" strokeLinecap="round" />
        <path d="M7.5 14h2M11 14h2M14.5 14h2M7.5 17.5h2M11 17.5h2" strokeLinecap="round" />
      </svg>
    </span>
  );
}
