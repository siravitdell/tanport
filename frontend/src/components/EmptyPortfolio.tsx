import Link from "next/link";

/** "No holdings yet" with the way out: record the first buy. */
export function EmptyPortfolio({ className = "" }: { className?: string }) {
  return (
    <span className={className}>
      ยังไม่มีหุ้นในพอร์ต ·{" "}
      <Link href="/portfolio" className="font-medium underline">
        บันทึกการซื้อ
      </Link>
    </span>
  );
}
