export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-[8px] border border-dashed border-border-strong px-6 py-14 text-center">
      <p className="text-[18px] font-bold text-ink">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-md text-[15px] leading-[1.7] text-ink-soft">{body}</p>}
    </div>
  );
}
