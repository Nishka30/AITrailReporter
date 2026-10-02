import Image from "next/image";
import Link from "next/link";
import type { PublicLocationCategory, PublicObservation, PublicResearchFinding } from "@/lib/content";
import { categoryStateLabel, categoryStateTone, formatDate } from "@/lib/content/freshness";
import { shortTitle } from "@/lib/content/guide";
import { Avatar, StatusChip, TextLink, type ChipTone } from "./primitives";
import { Icon, type IconName } from "./Icons";
import { MapTile, MAP_ATTRIBUTION, type MapTilePin } from "./MapTile";

export interface Orientation {
  icon: IconName;
  title: string;
  text: string;
  link: { href: string; label: string };
}

/** The reference's "Arriving or flying out? / A little time in the village?
 * / Ready to start walking?" panel -- here built from what the page holds. */
export function OrientationPanel({ items }: { items: Orientation[] }) {
  if (items.length === 0) return null;
  const cols = ["md:grid-cols-1", "md:grid-cols-2", "md:grid-cols-3"][items.length - 1] ?? "md:grid-cols-3";
  return (
    <div className={`grid overflow-hidden rounded-[7px] border border-border-soft bg-[#f4f8f8] ${cols}`}>
      {items.map((item, i) => (
        <div key={item.title} className={`p-7 sm:p-8 ${i > 0 ? "border-t border-border-soft md:border-l md:border-t-0" : ""}`}>
          <Icon name={item.icon} size={24} strokeWidth={1.5} className="text-accent-deep" />
          <h3 className="mt-4 text-[19px] font-bold tracking-[-0.015em] text-ink">{item.title}</h3>
          <p className="mt-2.5 text-[15.5px] leading-[1.75] text-ink-soft">{item.text}</p>
          <div className="mt-4">
            <TextLink href={item.link.href}>{item.link.label}</TextLink>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CtaBand({ eyebrow, title, text, href, button, caption }: { eyebrow: string; title: React.ReactNode; text: string; href: string; button: string; caption: string }) {
  return (
    <div className="grid gap-8 rounded-[8px] bg-deep px-7 py-10 text-white sm:px-11 md:grid-cols-[1.6fr_1fr] md:items-center">
      <div>
        <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-[#9fd3e2]">{eyebrow}</p>
        <h2 className="mt-3 text-[28px] font-bold leading-[1.22] tracking-[-0.025em] sm:text-[31px]">{title}</h2>
        <p className="mt-3 text-[16.5px] leading-[1.7] text-white/85">{text}</p>
      </div>
      <div>
        <a href={href} className="inline-flex min-h-[46px] items-center gap-2.5 rounded-[5px] bg-cta px-5 text-[15.5px] font-bold text-cta-ink hover:bg-cta-deep">
          {button}
          <Icon name="chat" size={17} strokeWidth={1.9} />
        </a>
        <p className="mt-3 max-w-[260px] text-[13px] leading-[1.6] text-white/75">{caption}</p>
      </div>
    </div>
  );
}

export interface ExploreCard {
  eyebrow: string;
  title: string;
  text: string;
  href: string;
  map: MapTilePin;
  zoom?: number;
}

/** "Where will you go from here?" -- image-led cards; the image is a real
 * map of the destination. */
export function ExploreCards({ cards }: { cards: ExploreCard[] }) {
  return (
    <div className="grid gap-6 md:grid-cols-3">
      {cards.map((c) => (
        <Link key={c.href + c.title} href={c.href} className="group overflow-hidden rounded-[8px] border border-border bg-white transition-colors hover:border-border-strong">
          <div className="relative h-[170px]">
            <MapTile center={c.map} zoom={c.zoom ?? 13} className="absolute inset-0" />
            <span className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-full bg-white text-ink">
              <Icon name="arrowUpRight" size={15} strokeWidth={2} />
            </span>
          </div>
          <div className="px-6 pb-6 pt-5">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.14em] text-ink-meta">{c.eyebrow}</p>
            <h3 className="mt-2 text-[19px] font-bold tracking-[-0.015em] text-ink group-hover:text-accent-deep">{c.title}</h3>
            <p className="mt-1.5 text-[15px] leading-[1.65] text-ink-soft">{c.text}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

const TONE_TO_CHIP: Record<string, ChipTone> = { good: "fresh", warn: "due", bad: "old", neutral: "old" };

/** Guide-verified facts as the reference's comparison table. */
export function VerifiedTable({ categories }: { categories: PublicLocationCategory[] }) {
  return (
    <div className="overflow-hidden rounded-[6px] border border-border">
      <div className="hidden grid-cols-[1fr_2fr_1.1fr] gap-6 border-b border-border bg-paper-muted px-5 py-4 text-[13.5px] text-ink-meta md:grid">
        <span>Topic</span>
        <span>What a guide confirmed</span>
        <span>When it was checked</span>
      </div>
      <ul className="divide-y divide-border">
        {categories.flatMap((c) =>
          c.verified_knowledge.map((k, i) => (
            <li key={k.knowledge_id} className="grid gap-3 px-5 py-5 md:grid-cols-[1fr_2fr_1.1fr] md:gap-6">
              <div>
                {i === 0 && (
                  <>
                    <p className="text-[16px] font-bold text-ink">{c.display_name}</p>
                    <p className="mt-1 text-[13.5px] text-ink-meta">{categoryStateLabel(c.state)}</p>
                  </>
                )}
              </div>
              <p className="text-[15.5px] leading-[1.7] text-ink">{k.knowledge_text}</p>
              <div className="space-y-2">
                <StatusChip tone={k.fresh ? "fresh" : TONE_TO_CHIP[categoryStateTone(c.state)] ?? "old"}>{k.fresh ? "Still current" : "Due for a re-check"}</StatusChip>
                <p className="text-[13.5px] text-ink-meta">Verified {formatDate(k.last_verified_at)}</p>
              </div>
            </li>
          )),
        )}
      </ul>
    </div>
  );
}

export function PhotoStrip({ observations }: { observations: PublicObservation[] }) {
  const photos = observations.filter((o) => o.photo_urls[0]).slice(0, 3);
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {photos.map((o) => (
        <Link key={o.observation_id} href={`/observations/${o.observation_id}`} className="group relative h-[270px] overflow-hidden rounded-[6px] bg-paper-muted">
          <Image src={o.photo_urls[0]!} alt="" fill sizes="(min-width: 768px) 33vw, 100vw" className="object-cover transition duration-500 group-hover:scale-[1.03]" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
          <Icon name="camera" size={18} className="absolute right-4 top-4 text-white" />
          <div className="absolute inset-x-5 bottom-4 text-white">
            <p className="text-[18px] font-bold [text-shadow:0_1px_2px_rgba(0,0,0,.4)]">{o.location_label ?? o.category_display_name ?? o.display_name}</p>
            <p className="mt-1 line-clamp-2 text-[13.5px] text-white/90">{o.evidence}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

export function GuideVoices({ observations }: { observations: PublicObservation[] }) {
  const quotes = observations.filter((o) => o.transcript).slice(0, 2);
  return (
    <div className="grid gap-7 md:grid-cols-2">
      {quotes.map((o) => (
        <article key={o.observation_id} className="border-t-[3px] border-[#b9c9c4] bg-[#f3f6f4] p-8">
          <Icon name="book" size={22} strokeWidth={1.5} className="text-ink-meta" />
          <h3 className="mt-5 text-[21px] font-bold tracking-[-0.02em] text-ink">{o.category_display_name ?? o.display_name}</h3>
          <p className="mt-4 text-[17px] leading-[1.9] text-ink-soft">&ldquo;{o.transcript}&rdquo;</p>
          <div className="mt-6 flex items-center gap-3">
            <Avatar name={o.guide_name} size={40} />
            <div className="leading-tight">
              <p className="text-[13.5px] font-bold text-ink">{o.guide_name}</p>
              <p className="mt-1 text-[12.5px] text-ink-meta">Voice note · {formatDate(o.observed_at)}</p>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

export function SourcesSection({
  guideNames,
  findings,
  researchSources,
  questionCount,
  hubName,
}: {
  guideNames: string[];
  findings: PublicResearchFinding[];
  researchSources: { url: string; title: string | null }[];
  questionCount: number;
  hubName: string | null;
}) {
  const sources = [...researchSources, ...findings.flatMap((f) => f.sources)].filter(
    (s, i, all) => all.findIndex((x) => x.url === s.url) === i,
  );
  return (
    <div className="grid gap-10 border-t border-border pt-12 md:grid-cols-[1fr_1.6fr]">
      <div>
        <p className="eyebrow">Sources &amp; contributors</p>
        <h2 className="mt-3 text-[29px] font-bold leading-[1.2] tracking-[-0.025em] text-ink">
          Local detail.
          <br />
          Visible evidence.
        </h2>
        <div className="mt-5">
          <TextLink href="/#trust" icon="arrowUpRight">
            How this guide works
          </TextLink>
        </div>
      </div>
      <div className="space-y-5 text-[16px] leading-[1.8] text-ink-soft">
        <p>
          <strong className="font-semibold text-ink">Guide observations:</strong>{" "}
          {guideNames.length > 0
            ? `dated reports by ${guideNames.join(", ")}. Every report keeps its visit date, contributor and the spot it describes, and was reviewed before it appeared here.`
            : "no guide has reported here yet. Reports appear on this page once they are reviewed."}
        </p>
        {questionCount > 0 && (
          <p>
            <strong className="font-semibold text-ink">Questions:</strong> {questionCount} curated question{questionCount === 1 ? "" : "s"}
            {hubName ? ` for the ${hubName} area` : ""}. An unanswered question means no guide has checked it yet — not that there is no answer.
          </p>
        )}
        {sources.length > 0 && (
          <p>
            <strong className="font-semibold text-ink">Background research:</strong>{" "}
            {sources.slice(0, 8).map((s, i) => (
              <span key={s.url}>
                {i > 0 && ", "}
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-accent-deep underline underline-offset-2">
                  {shortTitle(s.title, s.url)}
                </a>
              </span>
            ))}
            . Web research describes what sources claim; it is never presented as a guide&rsquo;s confirmation.
          </p>
        )}
        <p className="text-[14px] text-ink-meta">Maps: {MAP_ATTRIBUTION}. Maps show location only, not trail conditions.</p>
      </div>
    </div>
  );
}
