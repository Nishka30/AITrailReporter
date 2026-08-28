import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-border bg-paper-muted">
      <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8">
        <div className="grid gap-10 sm:grid-cols-[1.3fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-ink font-heading text-xs font-extrabold text-marigold-soft">
                F
              </span>
              <p className="font-heading text-lg font-bold text-ink">Firsthand</p>
            </div>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-soft">
              What a place is like right now, from people who were actually there. Every
              report on this site passed a human review before it went live.
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Explore</p>
            <ul className="mt-3 space-y-2 text-sm text-ink-soft">
              <li>
                <Link href="/explore" className="transition hover:text-ink">
                  All places
                </Link>
              </li>
              <li>
                <Link href="/explore?has_photos=true" className="transition hover:text-ink">
                  Photos
                </Link>
              </li>
              <li>
                <Link href="/explore?has_voice=true" className="transition hover:text-ink">
                  Voice stories
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">About this data</p>
            <p className="mt-3 text-sm leading-relaxed text-ink-soft">
              Reports come from local guides in the field and are checked by a moderation
              team before publishing. Nothing here is generated or estimated.
            </p>
          </div>
        </div>
        <p className="mt-12 text-xs text-ink-faint">© {new Date().getFullYear()} Firsthand. Built on real, moderated field reports.</p>
      </div>
    </footer>
  );
}
