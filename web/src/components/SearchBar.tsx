"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export function SearchBar({
  initialQuery = "",
  compact = false,
}: {
  initialQuery?: string;
  compact?: boolean;
}) {
  const [query, setQuery] = useState(initialQuery);
  const router = useRouter();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q) router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <form onSubmit={onSubmit} className="relative w-full" role="search">
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a place, trail, or condition…"
        aria-label="Search"
        className={
          compact
            ? "w-full rounded-full border border-border/80 bg-paper-elevated/80 py-2 pl-4 pr-10 text-sm text-ink placeholder:text-ink-faint outline-none backdrop-blur-sm transition focus:border-marigold-deep focus:bg-paper-elevated focus:ring-4 focus:ring-marigold-soft/70"
            : "w-full rounded-2xl border border-white/15 bg-white/95 py-4.5 pl-6 pr-16 text-base text-ink shadow-warm-lg placeholder:text-ink-faint outline-none backdrop-blur-md transition focus:ring-4 focus:ring-marigold-soft/80"
        }
      />
      <button
        type="submit"
        aria-label="Search"
        className={
          compact
            ? "absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center justify-center rounded-full bg-ink p-2 text-paper transition hover:bg-marigold-deep active:scale-90"
            : "absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center justify-center rounded-xl bg-ink p-3 text-paper transition hover:bg-marigold-deep active:scale-90"
        }
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
      </button>
    </form>
  );
}
