"use client";

export default function Error({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="mx-auto max-w-lg px-5 py-32 text-center">
      <p className="font-heading text-2xl font-bold text-ink">Couldn&rsquo;t load this report</p>
      <p className="mt-3 text-sm text-ink-soft">Something went wrong reaching the backend. Try again in a moment.</p>
      <button
        type="button"
        onClick={() => retry()}
        className="mt-6 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition hover:bg-marigold-deep"
      >
        Try again
      </button>
    </div>
  );
}
