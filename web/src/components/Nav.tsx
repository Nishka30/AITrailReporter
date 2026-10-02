import Link from "next/link";
import { SearchBar } from "./SearchBar";
import { Icon } from "./guide/Icons";

function Mark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <circle cx="20" cy="20" r="19" fill="#13a3cf" />
      <path d="M7 29 16 15l4.5 7 3.5-5L33 29Z" fill="#fff" />
      <path d="M16 15l2.2 3.4-1.3 2.1-.9-1.4-1.4 2.2-1.4-.9Z" fill="#13a3cf" />
    </svg>
  );
}

export function Logo({ light = true }: { light?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <Mark className="h-9 w-9" />
      <span
        className={`font-heading text-[22px] font-extrabold uppercase leading-none tracking-[-0.01em] ${light ? "text-white" : "text-ink"}`}
      >
        Firsthand
      </span>
    </span>
  );
}

/**
 * The reference guide's two-tier header: brand bar (logo, tagline, primary
 * yellow action) over a darker link row. Deliberately NOT sticky -- it
 * scrolls away and each page's own section bar pins to the top instead.
 */
export function Nav() {
  return (
    <header className="relative z-30 bg-header text-white">
      <div className="page flex min-h-[86px] items-center gap-5 py-3">
        <Link href="/" aria-label="Firsthand home" className="shrink-0">
          <Logo />
        </Link>
        <span className="hidden h-10 w-px bg-white/20 md:block" />
        <p className="hidden text-[13px] leading-[1.5] text-white/80 md:block">
          Local knowledge.
          <br />
          Straight from the trail.
        </p>

        <div className="ml-auto hidden w-[280px] lg:block">
          <SearchBar compact />
        </div>
        <Link
          href="/search"
          aria-label="Search"
          className="ml-auto flex h-10 w-10 items-center justify-center rounded-[5px] text-white/80 hover:bg-white/10 lg:hidden"
        >
          <Icon name="search" size={20} />
        </Link>
        <Link
          href="/#ask"
          className="hidden min-h-[44px] shrink-0 items-center gap-2.5 rounded-[5px] bg-cta px-[18px] text-[15px] font-bold text-cta-ink transition hover:bg-cta-deep sm:inline-flex"
        >
          Ask a local guide
          <Icon name="arrowUpRight" size={16} strokeWidth={2} />
        </Link>
      </div>

      <nav aria-label="Main" className="bg-header-deep">
        <div className="page rail flex h-[46px] items-center gap-8 overflow-x-auto text-[14px]">
          <Link href="/" className="shrink-0 text-white/90 hover:text-white">Home</Link>
          <Link href="/explore" className="shrink-0 text-white/90 hover:text-white">Places</Link>
          <Link href="/routes" className="shrink-0 text-white/90 hover:text-white">Routes</Link>
          <Link href="/explore#reports" className="shrink-0 text-white/90 hover:text-white">Latest reports</Link>
          <Link href="/#trust" className="shrink-0 text-white/90 hover:text-white">How we report</Link>
          <Link href="/#right-now" className="ml-auto flex shrink-0 items-center gap-2 text-[13px] text-white/90 hover:text-white">
            <span className="h-2 w-2 rounded-full bg-ok-dot" />
            The guides&rsquo; notebook
          </Link>
        </div>
      </nav>
    </header>
  );
}
