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
            ? "w-full rounded-[5px] border border-white/15 bg-white/10 py-2.5 pl-4 pr-10 text-[14px] text-white placeholder:text-white/55 outline-none transition focus:border-white/40 focus:bg-white/15"
            : "w-full rounded-[5px] border border-border-strong bg-white py-4 pl-5 pr-16 text-[16px] text-ink placeholder:text-ink-faint outline-none transition focus:border-accent focus:ring-2 focus:ring-accent-soft"
        }
      />
      <button
        type="submit"
        aria-label="Search"
        className={
          compact
            ? "absolute right-1 top-1/2 flex -translate-y-1/2 items-center justify-center rounded-[4px] p-2 text-white/80 transition hover:text-white"
            : "absolute right-2 top-1/2 flex -translate-y-1/2 items-center justify-center rounded-[5px] bg-accent-deep p-3 text-white transition hover:bg-accent"
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
