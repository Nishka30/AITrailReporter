import Link from "next/link";
import { content } from "@/lib/content";
import type { PublicRoute } from "@/lib/content";
import { AskAnything } from "@/components/AskAnything";
import { reportTabKeys, stateByAge, type LocalCheck } from "@/lib/content/locationPage";
import { isWithinLastDays, recentDateRangeLabel } from "@/lib/content/freshness";
import { dateTime, nowMs } from "@/lib/content/guide";
import { PageHero, LatestCheck, type HeroVisual } from "@/components/guide/PageHero";
import { SectionNav } from "@/components/guide/SectionNav";
import { ButtonLink, SectionHeader, TextLink } from "@/components/guide/primitives";
import { FilterGrid } from "@/components/guide/FilterGrid";
import { ReportCard } from "@/components/guide/ReportCard";
import { QuestionsSection } from "@/components/guide/Questions";
import { ExploreCards, type ExploreCard } from "@/components/guide/Blocks";
import { RouteFeature, routeCenter, routeZoom } from "@/components/guide/RouteFeature";
import { GuideCards, WeekDigest, guideStats } from "@/components/guide/RouteParts";
import { Band } from "@/components/guide/Planning";
import { Icon, type IconName } from "@/components/guide/Icons";

function Section({ id, children, className = "" }: { id?: string; children: React.ReactNode; className?: string }) {
  return (
    <section id={id} className={`page scroll-mt-[76px] py-14 sm:py-16 ${className}`}>
      {children}
    </section>
  );
}

function joinNames(names: string[]): string {
  return names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

const TRUST: { icon: IconName; title: string; text: string }[] = [
  {
    icon: "clock",
    title: "Local checks",
    text: "One guide's dated report from one visit — who, where and exactly when. A record of a visit, never a guarantee for yours.",
  },
  {
    icon: "check",
    title: "Verified by guides",
    text: "A fact a reviewed guide report confirmed on the ground, with the date it was last checked. Facts expire and get re-checked.",
  },
  {
    icon: "book",
    title: "Background research",
    text: "What public web sources say about a place, with links. Useful for planning, always labelled — never shown as a guide's check.",
  },
];

/**
 * The region hub, in the reference guide's order: hero -> the field
 * notebook -> the week in perspective -> current answers -> ask -> areas and
 * routes -> guides -> how we report. Areas are the curated hubs; routes the
 * seeded routes; everything else is approved guide content.
 */
export default async function HomePage() {
  const [recent, hubs, routeSummaries, locations] = await Promise.all([
    content.listObservations({ limit: 40 }),
    content.listHubs(),
    content.listRoutes(),
    content.listLocations(60),
  ]);
  const [hubDetails, routes] = await Promise.all([
    Promise.all(hubs.map((h) => content.getLocation(h.location_id))),
    Promise.all(routeSummaries.map((r) => content.getRoute(r.slug))),
  ]);
  const realRoutes = routes.filter((r): r is PublicRoute => Boolean(r && r.stops.length));
  const now = nowMs();

  const observations = recent.items;
  const checks: LocalCheck[] = observations.map((o) => ({
    observation: o,
    label: o.category_display_name ?? o.display_name,
    state: stateByAge(o.observed_at),
  }));
  const topicTabs = [...new Map(checks.map((c) => [reportTabKeys(c.observation)[0], c.label])).entries()]
    .map(([key, label]) => ({ key, label }))
    .slice(0, 6);
  const thisWeek = observations.filter((o) => isWithinLastDays(o.observed_at, 7));
  const guides = guideStats(observations, (o) => o.nearest_place_name ?? o.location_label ?? null);
  const answered = hubDetails.flatMap((d) => d?.popular_questions ?? []);
  const open = hubDetails.flatMap((d) => d?.open_questions ?? []);
  const latest = observations[0] ?? null;
  const hubNames = hubs.map((h) => h.name);

  const photo = observations.find((o) => o.photo_urls[0]);
  const featuredHub = hubs[0] ?? null;
  const visual: HeroVisual | null = photo
    ? { kind: "photo", url: photo.photo_urls[0]!, caption: photo.location_label ?? photo.nearest_place_name ?? "", tag: `Guide photo · ${dateTime(photo.observed_at)}` }
    : realRoutes[0]
      ? {
          kind: "map",
          center: { ...routeCenter(realRoutes[0]), label: realRoutes[0].name },
          pins: realRoutes[0].stops.map((s) => ({ latitude: s.latitude, longitude: s.longitude, label: s.name })),
          caption: realRoutes[0].name,
          zoom: routeZoom(realRoutes[0]),
          line: true,
          scale: 0.72,
        }
      : featuredHub
        ? { kind: "map", center: { latitude: featuredHub.latitude, longitude: featuredHub.longitude, label: featuredHub.name }, pins: [], caption: featuredHub.name }
        : null;

  const areaCards: ExploreCard[] = [
    ...hubs.map((h, i) => ({
      eyebrow: "Area guide",
      title: h.name,
      text: [
        hubDetails[i]?.nearby.length ? `${hubDetails[i]!.nearby.length} places` : null,
        h.open_question_count ? `${h.open_question_count + (hubDetails[i]?.popular_questions.length ?? 0)} questions travellers ask` : null,
        h.approved_observation_count ? `${h.approved_observation_count} guide reports` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      href: `/places/${h.location_id}`,
      map: { latitude: h.latitude, longitude: h.longitude, label: h.name },
      zoom: 15,
    })),
    ...realRoutes.map((r) => ({
      eyebrow: "Route",
      title: r.name,
      text: r.stops.map((s) => s.name).filter((_, i, a) => i === 0 || i === a.length - 1).join(" → "),
      href: `/routes/${r.slug}`,
      map: { ...routeCenter(r), label: r.name },
      zoom: routeZoom(r) - 1,
    })),
  ];

  const nav = [
    observations.length > 0 && { id: "right-now", label: "Right now" },
    thisWeek.length > 0 && { id: "this-week", label: "This week" },
    answered.length + open.length > 0 && { id: "answers", label: "Current answers" },
    areaCards.length > 0 && { id: "areas", label: "Areas & routes" },
    guides.length > 0 && { id: "guides", label: "Our guides" },
    { id: "trust", label: "How we report" },
  ].filter(Boolean) as { id: string; label: string }[];

  return (
    <div>
      <PageHero
        breadcrumb={[]}
        eyebrow="Local knowledge. Straight from the trail."
        title="See what a place"
        titleAccent="is really like."
        accentOnNewLine
        lede={`${hubNames.length ? `Area guides for ${joinNames(hubNames)}` : "Place guides"}${realRoutes.length ? `, the ${joinNames(realRoutes.map((r) => r.name))} stop by stop` : ""} — and dated reports from the local guides who walk there, season after season.`}
        status={
          <LatestCheck
            at={latest ? dateTime(latest.observed_at) : null}
            detail={guides.length ? `${guides.length} guide${guides.length === 1 ? "" : "s"} reporting · ${recent.total} reviewed reports` : null}
          />
        }
        actions={
          <>
            <ButtonLink href="#ask" variant="primary" icon="chat">
              Ask a local guide
            </ButtonLink>
            {realRoutes[0] && (
              <TextLink href={`/routes/${realRoutes[0].slug}`} icon="compass">
                Follow a route
              </TextLink>
            )}
          </>
        }
        visual={visual}
      />

      <SectionNav items={nav} action={{ href: "#ask", label: "Ask a guide", filled: true }} />

      {observations.length > 0 && (
        <Section id="right-now">
          <SectionHeader
            eyebrow="The field notebook"
            title="Right now, across every place"
            intro="Small details from recent visits. A clearer picture of the trail."
            aside={<TextLink href="#trust" icon="help" className="!font-normal !text-ink-soft">How we report</TextLink>}
          />
          <FilterGrid
            tabs={topicTabs}
            allLabel="All updates"
            trailing="Observed, dated, attributed."
            items={checks.map((check) => ({ id: check.observation.observation_id, keys: reportTabKeys(check.observation), node: <ReportCard check={check} /> }))}
            initialVisible={6}
            moreLabel="See more reports"
            footnote="recent field reports"
            emptyMessage="Nothing reported on this topic yet."
          />
        </Section>
      )}

      {thisWeek.length > 0 && (
        <section id="this-week" className="page scroll-mt-[76px] pb-6">
          <WeekDigest
            title={
              <>
                This week
                <br />
                on the ground.
              </>
            }
            range={recentDateRangeLabel(7)}
            observations={thisWeek}
          />
        </section>
      )}

      {answered.length + open.length > 0 && (
        <Section id="answers">
          <SectionHeader
            eyebrow="The questions we're hearing"
            title="Current answers, with the evidence"
            intro="What we know, who checked it, and what still needs another look."
            aside={
              <a href="#ask" className="inline-flex min-h-[48px] items-center gap-2.5 rounded-[5px] border border-border-strong bg-white px-5 text-[15.5px] font-semibold text-ink hover:border-ink-soft">
                Ask your question <Icon name="chat" size={17} strokeWidth={1.9} />
              </a>
            }
          />
          <QuestionsSection placeName="your trip" answered={answered} open={open} guideNames={guides.map((g) => g.name)} askHref="#ask" nowMs={now} />
        </Section>
      )}

      <section id="ask" className="page scroll-mt-[76px] pb-14">
        <div className="grid gap-8 rounded-[8px] bg-deep px-7 py-10 text-white sm:px-11 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <div>
            <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-[#9fd3e2]">Ask the people who know the trail</p>
            <h2 className="mt-3 text-[30px] font-bold leading-[1.2] tracking-[-0.025em] sm:text-[34px]">
              Ask a local guide who
              <br className="hidden sm:block" /> knows the trail.
            </h2>
            <p className="mt-4 text-[16.5px] leading-[1.75] text-white/85">
              Wondering what a place is like right now? Answers come only from dated, reviewed guide reports — never a guess.
            </p>
            {guides.length > 0 && <p className="mt-5 text-[14px] text-white/75">{joinNames(guides.slice(0, 4).map((g) => g.name))} report here.</p>}
          </div>
          <AskAnything locations={locations} />
        </div>
      </section>

      {areaCards.length > 0 && (
        <Section id="areas" className="!pt-4">
          <SectionHeader eyebrow="Follow your curiosity" title="From the routes and areas" intro="Go deeper into the part of the trail you're planning to visit." />
          <ExploreCards cards={areaCards} />
          {realRoutes[0] && (
            <div className="mt-10">
              <RouteFeature route={realRoutes[0]} />
            </div>
          )}
        </Section>
      )}

      {guides.length > 0 && (
        <Section id="guides" className="!pt-4">
          <SectionHeader eyebrow="The people behind the notebook" title="Our guides" intro="Every report is attributed to the guide who filed it." />
          <GuideCards guides={guides.slice(0, 8)} />
        </Section>
      )}

      <Band id="trust">
        <SectionHeader
          eyebrow="Open about what we know"
          title="Three kinds of information, never mixed together"
          intro="Every section on this site says which kind it is, so background never reads as today's conditions."
        />
        <div className="grid gap-px overflow-hidden rounded-[8px] border border-border bg-border md:grid-cols-3">
          {TRUST.map((t) => (
            <div key={t.title} className="bg-[#fdfdfb] p-7 sm:p-8">
              <Icon name={t.icon} size={24} strokeWidth={1.6} className="text-accent-deep" />
              <h3 className="mt-4 text-[20px] font-bold tracking-[-0.02em] text-ink">{t.title}</h3>
              <p className="mt-2.5 text-[15.5px] leading-[1.75] text-ink-soft">{t.text}</p>
            </div>
          ))}
        </div>
        <ol className="mt-10 grid gap-8 md:grid-cols-3">
          {[
            ["Someone on the ground reports it", "A local guide notes a condition, answers a question, or confirms a fact on a visit."],
            ["A person reviews it", "Every report is reviewed before it reaches this site — nothing publishes automatically."],
            ["It ages, honestly", "Each report keeps its date. When it gets old we say so, and ask the next guide to check again."],
          ].map(([title, text], i) => (
            <li key={title} className="flex gap-4">
              <span className="font-heading text-[26px] font-semibold text-[#9aaab3]">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <p className="text-[17px] font-bold text-ink">{title}</p>
                <p className="mt-1.5 text-[15px] leading-[1.7] text-ink-soft">{text}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-10 text-[14px] text-ink-meta">
          Looking for somewhere specific? <Link href="/explore" className="font-semibold text-accent-deep hover:underline">Browse every place</Link>.
        </p>
      </Band>
    </div>
  );
}
