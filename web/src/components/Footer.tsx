import Link from "next/link";
import { Logo } from "./Nav";
import { Icon } from "./guide/Icons";

const COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Explore",
    links: [
      { label: "All places", href: "/explore" },
      { label: "Routes", href: "/routes" },
      { label: "Latest reports", href: "/explore#reports" },
      { label: "Search", href: "/search" },
    ],
  },
  {
    title: "Before you go",
    links: [
      { label: "The guides' notebook", href: "/#right-now" },
      { label: "Questions travellers ask", href: "/#answers" },
      { label: "Ask a local guide", href: "/#ask" },
    ],
  },
  {
    title: "Firsthand",
    links: [
      { label: "How we report", href: "/#trust" },
      { label: "Sources & evidence", href: "/#trust" },
    ],
  },
];

export function Footer() {
  return (
    <footer>
      <section className="border-t border-border-soft bg-[#eef3f4]">
        <div className="page flex flex-wrap items-center justify-between gap-6 py-12">
          <div>
            <p className="eyebrow">Your journey starts with a question</p>
            <h2 className="mt-2 text-[29px] font-bold tracking-[-0.025em] text-ink">Let&rsquo;s find your trail.</h2>
            <p className="mt-1.5 text-[15px] text-ink-soft">Ask a local guide what you need to know before you go.</p>
          </div>
          <Link
            href="/#ask"
            className="inline-flex min-h-[48px] items-center gap-2.5 rounded-[5px] bg-cta px-6 text-[16px] font-bold text-cta-ink hover:bg-cta-deep"
          >
            Ask a local guide
            <Icon name="arrowUpRight" size={17} strokeWidth={2} />
          </Link>
        </div>
      </section>

      <div className="bg-footer text-white">
        <div className="page grid gap-10 py-14 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-5 text-[14px] leading-[1.7] text-white/75">
              Place guides built from dated local reports,
              <br />
              the questions travellers ask, and labelled research.
            </p>
          </div>
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <p className="text-[14px] font-bold">{col.title}</p>
              <ul className="mt-4 space-y-3 text-[13.5px] text-white/75">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="hover:text-white">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="page flex flex-wrap justify-between gap-3 border-t border-white/10 py-6 text-[12px] text-white/60">
          <p>© {new Date().getFullYear()} Firsthand. Every guide report is reviewed before it appears.</p>
          <p>Background research is labelled as research — never as a guide&rsquo;s report.</p>
        </div>
      </div>
    </footer>
  );
}
