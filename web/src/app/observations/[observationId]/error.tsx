"use client";

export default function Error({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="page flex min-h-[50vh] flex-col justify-center py-20">
      <p className="eyebrow">Something went wrong</p>
      <h1 className="mt-3 text-[34px] font-bold tracking-[-0.03em] text-ink">Couldn&rsquo;t load this report.</h1>
      <p className="mt-3 max-w-xl text-[16.5px] leading-[1.75] text-ink-soft">We couldn&rsquo;t reach our reports just now. Try again in a moment.</p>
      <div className="mt-7">
        <button
          type="button"
          onClick={() => retry()}
          className="inline-flex min-h-[44px] items-center rounded-[5px] bg-accent-deep px-5 text-[15px] font-bold text-white hover:bg-accent"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
