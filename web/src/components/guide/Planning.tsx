import Link from "next/link";
import type { PlaceResearchSummary, PublicResearchFinding, PublicRoute, PublicRouteStop } from "@/lib/content";
import { formatDate } from "@/lib/content/freshness";
import { findingQuestion, hostnameOf, researchBlocks, routeNeighbours, shortTitle } from "@/lib/content/guide";
import { CardEyebrow, SectionHeader } from "./primitives";
import { Icon, type IconName } from "./Icons";

/** The reference's warm "planning foundations" band -- background content,
 * visually set apart from the dated reports above it. */
export function Band({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-[1280px] scroll-mt-[76px] bg-band">
      <div className="page py-12 sm:py-14">{children}</div>
    </section>
  );
}

function StepCard({ eyebrow, icon, title, text, href }: { eyebrow: string; icon: IconName; title: string; text: string; href?: string }) {
  const body = (
    <>
      <CardEyebrow className="tracking-[0.16em]">{eyebrow}</CardEyebrow>
      <Icon name={icon} size={22} strokeWidth={1.6} className="mt-3 text-[#5d6f63]" />
      <h3 className="mt-3 text-[19px] font-bold tracking-[-0.015em] text-ink">{title}</h3>
      <p className="mt-2 text-[15.5px] leading-[1.7] text-ink-soft">{text}</p>
    </>
  );
  const cls = "block h-full rounded-[6px] border border-border bg-[#fdfdfb] p-6";
  return href ? (
    <Link href={href} className={`${cls} transition-colors hover:border-border-strong`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function elev(stop: PublicRouteStop): string {
  return stop.elevation_meters != null ? ` at ${stop.elevation_meters.toLocaleString()} m` : "";
}

export function JourneySteps({ route, locationId }: { route: PublicRoute; locationId: string }) {
  const { stops, index, previous, current, next } = routeNeighbours(route, locationId);
  if (!current) return null;
  const cards = [
    previous
      ? { eyebrow: "Before here", icon: "arrowRight" as IconName, title: `From ${previous.name}`, text: `Stop ${previous.sequence_order} of ${stops.length}${elev(previous)}.`, href: `/places/${previous.location_id}` }
      : { eyebrow: "Arrive", icon: "plane" as IconName, title: `${route.name} starts here`, text: `${current.name} is the first stop on the route.` },
    { eyebrow: "This stop", icon: "pin" as IconName, title: current.stop_label ?? current.name, text: `Stop ${index + 1} of ${stops.length}${elev(current)}.` },
    next
      ? { eyebrow: "Walk onward", icon: "boots" as IconName, title: `Continue to ${next.name}`, text: `Stop ${next.sequence_order} of ${stops.length}${elev(next)}.`, href: `/places/${next.location_id}` }
      : { eyebrow: "The end of the route", icon: "flag" as IconName, title: `${route.name} ends here`, text: "The return follows the same valley." },
  ];
  return (
    <div className="grid items-stretch gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
      {cards.map((c, i) => (
        <div key={c.eyebrow} className="contents">
          {i > 0 && <Icon name="arrowRight" size={20} className="mx-auto hidden self-center text-ink-faint md:block" />}
          <StepCard {...c} />
        </div>
      ))}
    </div>
  );
}

export function ResearchEssay({ summary, skip }: { summary: PlaceResearchSummary; skip?: "description" | "known_for" | null }) {
  const left = [
    skip !== "description" && summary.description ? { h: "What it is", t: summary.description } : null,
    skip !== "known_for" && summary.known_for ? { h: "Known for", t: summary.known_for } : null,
    summary.practical_info ? { h: "Good to know before you go", t: summary.practical_info } : null,
  ].filter(Boolean) as { h: string; t: string }[];
  return (
    <div className="grid gap-10 md:grid-cols-2 md:gap-0">
      <div className="space-y-7 md:border-r md:border-border md:pr-10">
        {left.map((b) => (
          <div key={b.h}>
            <h3 className="text-[20px] font-bold tracking-[-0.02em] text-ink">{b.h}</h3>
            <p className="mt-3 text-[16.5px] leading-[1.85] text-ink-soft">{b.t}</p>
          </div>
        ))}
      </div>
      <div className="space-y-7 md:pl-10">
        {summary.things_to_do.length > 0 && (
          <div>
            <h3 className="text-[20px] font-bold tracking-[-0.02em] text-ink">Make the time your own</h3>
            <ol className="mt-4 space-y-3">
              {summary.things_to_do.map((t, i) => (
                <li key={t} className="flex gap-4 text-[16px] leading-[1.7] text-ink-soft">
                  <span className="w-6 shrink-0 font-heading text-[15px] text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                  {t}
                </li>
              ))}
            </ol>
          </div>
        )}
        {summary.important_facts.length > 0 && (
          <div>
            <h3 className="text-[20px] font-bold tracking-[-0.02em] text-ink">Key facts</h3>
            <ul className="mt-3 space-y-2 text-[16px] leading-[1.7] text-ink-soft">
              {summary.important_facts.map((f) => (
                <li key={f} className="flex gap-3">
                  <span className="mt-[11px] h-1 w-1 shrink-0 rounded-full bg-ink-faint" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}
        {summary.warnings.length > 0 && (
          <div className="rounded-[6px] border border-[#ecd9a8] bg-[#fbf6e7] p-5">
            <p className="flex items-center gap-2 text-[14px] font-bold text-marigold-deep">
              <Icon name="flag" size={16} /> Worth knowing
            </p>
            <ul className="mt-2 space-y-1.5 text-[15px] leading-[1.7] text-ink">
              {summary.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function FindingBody({ finding }: { finding: PublicResearchFinding }) {
  const blocks = researchBlocks(finding.summary);
  return (
    <div className="grid gap-8 pb-7 lg:grid-cols-[1.6fr_1fr]">
      <div className="space-y-4 text-[16px] leading-[1.85] text-ink-soft">
        {blocks.map((b, i) =>
          b.kind === "p" ? (
            <p key={i}>{b.text}</p>
          ) : (
            <div key={i}>
              {b.heading && <p className="font-semibold text-ink">{b.heading}</p>}
              <ul className="mt-2 space-y-2">
                {b.items.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span className="mt-[12px] h-1 w-1 shrink-0 rounded-full bg-ink-faint" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">Sources</p>
        <ul className="mt-3 space-y-2.5 text-[14px] leading-[1.5]">
          {finding.sources.slice(0, 6).map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-accent-deep underline decoration-accent/30 underline-offset-2 hover:decoration-accent">
                {shortTitle(s.title, s.url)}
              </a>
              <span className="block text-[12px] text-ink-faint">{hostnameOf(s.url)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[12.5px] leading-[1.6] text-ink-faint">
          Researched {formatDate(finding.retrieved_at)} from public web sources. Not checked on the ground by a guide.
        </p>
      </div>
    </div>
  );
}

/** Research findings as the reference's planning-band FAQ rows. */
export function FindingAccordions({ findings }: { findings: PublicResearchFinding[] }) {
  return (
    <div className="divide-y divide-border border-y border-border">
      {findings.map((f, i) => (
        <details key={f.finding_id} className="group" open={i === 0}>
          <summary className="flex cursor-pointer items-center justify-between gap-6 py-5">
            <span className="text-[16.5px] font-semibold text-ink">{findingQuestion(f)}</span>
            <Icon name="chevronDown" size={18} className="shrink-0 text-ink-meta transition-transform group-open:rotate-180" />
          </summary>
          <FindingBody finding={f} />
        </details>
      ))}
    </div>
  );
}

export function PlanningHeader({ name }: { name: string }) {
  return (
    <SectionHeader
      eyebrow="Area reference · the planning foundations"
      title={`How ${name} fits into your journey`}
      intro="The steady background behind the local checks — route position and published research, kept separate from the dated reports above."
    />
  );
}
