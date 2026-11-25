/** Placeholder for pages that are not built yet. */
export function ComingSoon({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <h1 className="text-4xl font-bold">{title}</h1>
      <div className="mt-8 rounded-2xl border border-dashed border-line-strong bg-surface p-10 text-center text-muted">
        กำลังสร้าง: {note}
      </div>
    </section>
  );
}
