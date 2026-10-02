export default function Loading() {
  return (
    <div className="page animate-pulse pb-20 pt-9" aria-busy="true" aria-label="Loading">
      <div className="h-3 w-40 rounded bg-paper-muted" />
      <div className="mt-6 grid gap-10 lg:grid-cols-[1.35fr_1fr]">
        <div>
          <div className="h-3 w-32 rounded bg-paper-muted" />
          <div className="mt-4 h-12 w-3/4 rounded bg-paper-muted" />
          <div className="mt-5 h-4 w-full rounded bg-paper-muted" />
          <div className="mt-2 h-4 w-5/6 rounded bg-paper-muted" />
        </div>
        <div className="h-[260px] rounded-[8px] bg-paper-muted" />
      </div>
      <div className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-[360px] rounded-[8px] border border-border-soft bg-paper-muted/60" />
        ))}
      </div>
    </div>
  );
}
