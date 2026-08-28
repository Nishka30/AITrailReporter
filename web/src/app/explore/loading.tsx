export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl animate-pulse px-5 py-14 sm:px-8">
      <div className="h-8 w-40 rounded bg-paper-muted" />
      <div className="mt-4 h-4 w-96 max-w-full rounded bg-paper-muted" />
      <div className="mt-8 flex gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-8 w-24 rounded-full bg-paper-muted" />
        ))}
      </div>
      <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="aspect-[4/3] rounded-3xl bg-paper-muted" />
        ))}
      </div>
    </div>
  );
}
