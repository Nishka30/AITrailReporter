import Link from "next/link";
import { SearchBar } from "./SearchBar";

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-paper/75 backdrop-blur-xl backdrop-saturate-150 supports-[backdrop-filter]:bg-paper/60">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-5 py-3.5 sm:px-8">
        <Link href="/" className="group flex shrink-0 items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-ink font-heading text-sm font-extrabold text-marigold-soft transition group-hover:bg-marigold-deep group-hover:text-ink">
            F
          </span>
          <span className="font-heading text-lg font-extrabold tracking-tight text-ink">Firsthand</span>
        </Link>
        <nav className="hidden items-center gap-1 text-sm font-medium text-ink-soft md:flex">
          <NavLink href="/explore">Explore</NavLink>
          <NavLink href="/explore?has_photos=true">Photos</NavLink>
          <NavLink href="/explore?has_voice=true">Voice stories</NavLink>
        </nav>
        <div className="ml-auto hidden max-w-xs flex-1 sm:block">
          <SearchBar compact />
        </div>
        <Link
          href="/search"
          aria-label="Search"
          className="ml-auto flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink-soft transition hover:border-ink hover:text-ink sm:hidden"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </Link>
      </div>
    </header>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="rounded-full px-3.5 py-2 transition hover:bg-paper-muted hover:text-ink">
      {children}
    </Link>
  );
}
