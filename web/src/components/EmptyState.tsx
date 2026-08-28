export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-[28px] border border-dashed border-border-strong bg-paper-muted/50 px-6 py-16 text-center">
      <p className="font-heading text-lg font-semibold text-ink">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-ink-soft">{body}</p>}
    </div>
  );
}
